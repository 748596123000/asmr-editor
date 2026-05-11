import os
import shutil
from dataclasses import dataclass
from typing import List, Optional

from src.utils.ffmpeg_runner import (
    FFmpegError,
    FFmpegRunner,
    InvalidPathError,
    validate_file_path,
    validate_output_path,
)


_SUPPORTED_FORMATS = frozenset({"mp4", "mov", "mkv", "avi", "webm"})


@dataclass
class ProcessingConfig:
    output_format: str = "mp4"
    video_codec: str = "libx264"
    audio_codec: str = "aac"
    fade_duration: float = 0.5


@dataclass
class Segment:
    start: float
    end: float


class VideoProcessor:
    def __init__(self, runner: Optional[FFmpegRunner] = None):
        self._runner = runner or FFmpegRunner()

    @staticmethod
    def _validate_format(output_format: str) -> str:
        fmt = output_format.lower().lstrip(".")
        if fmt not in _SUPPORTED_FORMATS:
            raise ValueError(
                f"Unsupported output format: {output_format!r}. "
                f"Supported formats: {sorted(_SUPPORTED_FORMATS)}"
            )
        return fmt

    @staticmethod
    def _validate_segments(segments: List[Segment]) -> None:
        if not segments:
            raise ValueError("Segments list must not be empty")
        for seg in segments:
            if seg.start < 0:
                raise ValueError(
                    f"Segment start time must be non-negative, got {seg.start}"
                )
            if seg.end <= seg.start:
                raise ValueError(
                    f"Segment end time must be greater than start time: "
                    f"start={seg.start}, end={seg.end}"
                )

    def cut_segments(
        self,
        input_path: str,
        segments: List[Segment],
        output_path: str,
        config: Optional[ProcessingConfig] = None,
    ) -> str:
        resolved_input = validate_file_path(input_path)
        resolved_output = validate_output_path(output_path)
        config = config or ProcessingConfig()

        fmt = self._validate_format(config.output_format)
        self._validate_segments(segments)

        if len(segments) == 1:
            seg = segments[0]
            args = [
                "-i", resolved_input,
                "-ss", str(seg.start),
                "-to", str(seg.end),
                "-c:v", config.video_codec,
                "-c:a", config.audio_codec,
                "-y",
                resolved_output,
            ]
        else:
            filter_parts = []
            for i, seg in enumerate(segments):
                filter_parts.append(
                    f"[0:v]trim=start={seg.start}:end={seg.end},"
                    f"setpts=PTS-STARTPTS[v{i}]"
                )
                filter_parts.append(
                    f"[0:a]atrim=start={seg.start}:end={seg.end},"
                    f"asetpts=PTS-STARTPTS[a{i}]"
                )

            concat_video_inputs = "".join(
                f"[v{i}]" for i in range(len(segments))
            )
            concat_audio_inputs = "".join(
                f"[a{i}]" for i in range(len(segments))
            )
            n = len(segments)
            filter_parts.append(
                f"{concat_video_inputs}concat=n={n}:v=1:a=0[vout]"
            )
            filter_parts.append(
                f"{concat_audio_inputs}concat=n={n}:v=0:a=1[aout]"
            )

            filter_complex = ";".join(filter_parts)

            args = [
                "-i", resolved_input,
                "-filter_complex", filter_complex,
                "-map", "[vout]",
                "-map", "[aout]",
                "-c:v", config.video_codec,
                "-c:a", config.audio_codec,
                "-y",
                resolved_output,
            ]

        result = self._runner.run_ffmpeg(
            args,
            input_paths=[resolved_input],
            output_paths=[resolved_output],
        )

        if not result.success:
            raise FFmpegError(
                f"Cut segments failed (code {result.returncode}): "
                f"{result.stderr[-500:]}"
            )

        return resolved_output

    def remove_speech_segments(
        self,
        input_path: str,
        speech_segments: List[Segment],
        output_path: str,
        config: Optional[ProcessingConfig] = None,
        total_duration: float = 0.0,
    ) -> str:
        resolved_input = validate_file_path(input_path)
        resolved_output = validate_output_path(output_path)
        config = config or ProcessingConfig()

        fmt = self._validate_format(config.output_format)

        if not speech_segments:
            try:
                shutil.copy2(resolved_input, resolved_output)
            except OSError as exc:
                raise FFmpegError(
                    f"Failed to copy video (no speech to remove): {exc}"
                ) from exc
            return resolved_output

        self._validate_segments(speech_segments)

        sorted_segments = sorted(speech_segments, key=lambda s: s.start)

        asmr_segments: List[Segment] = []
        current = 0.0

        for seg in sorted_segments:
            if current < seg.start:
                asmr_segments.append(Segment(start=current, end=seg.start))
            current = max(current, seg.end)

        if total_duration > 0:
            asmr_segments.append(Segment(start=current, end=total_duration))
        else:
            asmr_segments.append(Segment(start=current, end=float("inf")))

        asmr_segments = [s for s in asmr_segments if s.start < s.end]

        if not asmr_segments:
            raise FFmpegError(
                "No ASMR segments remain after removing speech"
            )

        filter_parts = []
        for i, seg in enumerate(asmr_segments):
            trim_end = f":end={seg.end}" if seg.end != float("inf") else ""
            filter_parts.append(
                f"[0:v]trim=start={seg.start}{trim_end},"
                f"setpts=PTS-STARTPTS[v{i}]"
            )
            filter_parts.append(
                f"[0:a]atrim=start={seg.start}{trim_end},"
                f"asetpts=PTS-STARTPTS[a{i}]"
            )

        if config.fade_duration > 0 and len(asmr_segments) > 1:
            faded_parts = []
            for i in range(len(asmr_segments)):
                fade_in = f"fade=t=in:st=0:d={config.fade_duration}"

                vf = f"[v{i}]{fade_in}[vf{i}]"
                af = f"[a{i}]afade=t=in:st=0:d={config.fade_duration}[af{i}]"

                faded_parts.append(vf)
                faded_parts.append(af)

            filter_parts = faded_parts

            concat_video_inputs = "".join(
                f"[vf{i}]" for i in range(len(asmr_segments))
            )
            concat_audio_inputs = "".join(
                f"[af{i}]" for i in range(len(asmr_segments))
            )
        else:
            concat_video_inputs = "".join(
                f"[v{i}]" for i in range(len(asmr_segments))
            )
            concat_audio_inputs = "".join(
                f"[a{i}]" for i in range(len(asmr_segments))
            )

        n = len(asmr_segments)
        filter_parts.append(
            f"{concat_video_inputs}concat=n={n}:v=1:a=0[vout]"
        )
        filter_parts.append(
            f"{concat_audio_inputs}concat=n={n}:v=0:a=1[aout]"
        )

        filter_complex = ";".join(filter_parts)

        args = [
            "-i", resolved_input,
            "-filter_complex", filter_complex,
            "-map", "[vout]",
            "-map", "[aout]",
            "-c:v", config.video_codec,
            "-c:a", config.audio_codec,
            "-y",
            resolved_output,
        ]

        result = self._runner.run_ffmpeg(
            args,
            input_paths=[resolved_input],
            output_paths=[resolved_output],
        )

        if not result.success:
            raise FFmpegError(
                f"Remove speech segments failed (code {result.returncode}): "
                f"{result.stderr[-500:]}"
            )

        return resolved_output

    def preview_segment(
        self,
        input_path: str,
        start: float,
        end: float,
        output_path: str,
    ) -> str:
        resolved_input = validate_file_path(input_path)
        resolved_output = validate_output_path(output_path)

        if start < 0:
            raise ValueError(f"Start time must be non-negative, got {start}")
        if end <= start:
            raise ValueError(
                f"End time must be greater than start time: start={start}, end={end}"
            )

        ext = os.path.splitext(resolved_output)[1].lower().lstrip(".")
        if ext and ext not in _SUPPORTED_FORMATS:
            raise ValueError(
                f"Unsupported preview format: {ext!r}. "
                f"Supported formats: {sorted(_SUPPORTED_FORMATS)}"
            )

        args = [
            "-i", resolved_input,
            "-ss", str(start),
            "-to", str(end),
            "-c:v", "libx264",
            "-crf", "23",
            "-preset", "fast",
            "-c:a", "aac",
            "-y",
            resolved_output,
        ]

        result = self._runner.run_ffmpeg(
            args,
            input_paths=[resolved_input],
            output_paths=[resolved_output],
        )

        if not result.success:
            raise FFmpegError(
                f"Preview segment failed (code {result.returncode}): "
                f"{result.stderr[-500:]}"
            )

        return resolved_output

    @staticmethod
    def get_supported_formats() -> List[str]:
        return sorted(_SUPPORTED_FORMATS)
