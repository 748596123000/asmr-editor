import json
from typing import Dict, Optional

import numpy as np

from src.utils.ffmpeg_runner import (
    FFmpegError,
    FFmpegRunner,
    InvalidPathError,
    validate_file_path,
    validate_output_path,
)
from src.utils.temp_manager import TempFileManager


class AudioExtractor:
    def __init__(self, runner: Optional[FFmpegRunner] = None):
        self._runner = runner or FFmpegRunner()
        self._temp_manager = TempFileManager()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup()
        return False

    def extract(
        self,
        video_path: str,
        output_path: Optional[str] = None,
    ) -> str:
        resolved_input = validate_file_path(video_path)

        if output_path is None:
            output_path = self._temp_manager.create_temp(suffix=".wav")
        else:
            output_path = validate_output_path(output_path)

        args = [
            "-i", resolved_input,
            "-vn",
            "-acodec", "pcm_s16le",
            "-ar", "16000",
            "-ac", "1",
            "-y",
            output_path,
        ]

        result = self._runner.run_ffmpeg(
            args,
            input_paths=[resolved_input],
            output_paths=[output_path],
        )

        if not result.success:
            raise FFmpegError(
                f"Audio extraction failed (code {result.returncode}): "
                f"{result.stderr[-500:]}"
            )

        return output_path

    def extract_to_numpy(self, video_path: str) -> tuple[np.ndarray, int]:
        wav_path = self.extract(video_path)

        try:
            from scipy.io import wavfile
            sample_rate, data = wavfile.read(wav_path)
        except ImportError:
            sample_rate, data = self._read_wav_manual(wav_path)

        if data.dtype != np.float32:
            data = data.astype(np.float32) / 32768.0

        return data, sample_rate

    def _read_wav_manual(self, wav_path: str) -> tuple[int, np.ndarray]:
        with open(wav_path, "rb") as f:
            f.read(4)
            f.read(4)
            f.read(4)
            f.read(4)
            chunk_size = int.from_bytes(f.read(4), "little")
            audio_format = int.from_bytes(f.read(2), "little")
            num_channels = int.from_bytes(f.read(2), "little")
            sample_rate = int.from_bytes(f.read(4), "little")
            f.read(4)
            bits_per_sample = int.from_bytes(f.read(2), "little")

            remaining_header = chunk_size - 16
            if remaining_header > 0:
                f.read(remaining_header)

            while True:
                chunk_id = f.read(4)
                if not chunk_id:
                    raise FFmpegError("Invalid WAV file: no data chunk found")
                chunk_size = int.from_bytes(f.read(4), "little")
                if chunk_id == b"data":
                    break
                f.read(chunk_size)

            num_bytes = chunk_size
            raw_data = f.read(num_bytes)

        if bits_per_sample == 16:
            data = np.frombuffer(raw_data, dtype=np.int16)
        elif bits_per_sample == 32:
            data = np.frombuffer(raw_data, dtype=np.int32)
        else:
            data = np.frombuffer(raw_data, dtype=np.int16)

        if num_channels > 1:
            data = data[::num_channels]

        return sample_rate, data

    def get_video_info(self, video_path: str) -> Dict:
        resolved = validate_file_path(video_path)

        args = [
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            resolved,
        ]

        result = self._runner.run_ffprobe(
            args,
            input_paths=[resolved],
        )

        if not result.success:
            raise FFmpegError(
                f"Failed to get video info (code {result.returncode}): "
                f"{result.stderr[-500:]}"
            )

        try:
            probe_data = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise FFmpegError(f"Failed to parse FFprobe output: {exc}") from exc

        info: Dict = {
            "duration": 0.0,
            "resolution": None,
            "video_codec": None,
            "audio_codec": None,
            "format": None,
        }

        fmt = probe_data.get("format", {})
        if fmt:
            info["duration"] = float(fmt.get("duration", 0.0))
            info["format"] = fmt.get("format_name")

        for stream in probe_data.get("streams", []):
            codec_type = stream.get("codec_type")
            if codec_type == "video" and info["video_codec"] is None:
                info["video_codec"] = stream.get("codec_name")
                width = stream.get("width")
                height = stream.get("height")
                if width and height:
                    info["resolution"] = (width, height)
            elif codec_type == "audio" and info["audio_codec"] is None:
                info["audio_codec"] = stream.get("codec_name")

        return info

    def cleanup(self):
        self._temp_manager.cleanup()
