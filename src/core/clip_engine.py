import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, List, Optional

from src.core.audio_extractor import AudioExtractor
from src.core.vad_detector import VADDetector
from src.core.video_processor import ProcessingConfig, Segment, VideoProcessor
from src.utils.validators import (
    validate_output_format,
    validate_positive_number,
    validate_threshold,
    validate_video_file,
)


class _SimpleSegment:
    def __init__(self, start: float, end: float):
        self.start = start
        self.end = end


class ProcessingStatus(Enum):
    IDLE = "idle"
    EXTRACTING_AUDIO = "extracting_audio"
    DETECTING_SPEECH = "detecting_speech"
    PROCESSING_VIDEO = "processing_video"
    COMPLETED = "completed"
    ERROR = "error"
    CANCELLED = "cancelled"


@dataclass
class ProcessingResult:
    status: ProcessingStatus
    input_path: Optional[str] = None
    output_path: Optional[str] = None
    speech_segments: list = field(default_factory=list)
    silence_segments: list = field(default_factory=list)
    original_duration: float = 0.0
    output_duration: float = 0.0
    error_message: Optional[str] = None


class ClipEngine:
    def __init__(
        self,
        vad_threshold: float = 0.5,
        min_speech_duration: float = 0.25,
        output_format: str = 'mp4',
    ):
        self._vad_threshold = validate_threshold(vad_threshold)
        self._min_speech_duration = validate_positive_number(
            min_speech_duration, name='min_speech_duration'
        )
        self._output_format = validate_output_format(output_format)

        self._audio_extractor = AudioExtractor()
        self._vad_detector = VADDetector(
            threshold=self._vad_threshold,
            min_speech_duration=self._min_speech_duration,
        )
        self._video_processor = VideoProcessor()

        self._status = ProcessingStatus.IDLE
        self._cancelled = False

    @property
    def status(self) -> ProcessingStatus:
        return self._status

    def _set_status(self, status: ProcessingStatus) -> None:
        self._status = status

    def _generate_output_path(self, video_path: str, output_dir: Optional[str] = None) -> str:
        base_name = os.path.splitext(os.path.basename(video_path))[0]
        output_filename = f"{base_name}_asmr.{self._output_format}"

        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
            return os.path.join(output_dir, output_filename)

        project_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        default_output_dir = os.path.join(project_dir, "output")
        os.makedirs(default_output_dir, exist_ok=True)
        return os.path.join(default_output_dir, output_filename)

    def process(
        self,
        video_path: str,
        output_path: Optional[str] = None,
        progress_callback: Optional[Callable[[ProcessingStatus, float], None]] = None,
    ) -> ProcessingResult:
        result = ProcessingResult(status=ProcessingStatus.IDLE)
        self._cancelled = False

        try:
            resolved_path = validate_video_file(video_path)
            result.input_path = resolved_path
            validate_output_format(self._output_format)

            video_info = self._audio_extractor.get_video_info(resolved_path)
            result.original_duration = video_info.get("duration", 0.0)

            if output_path is None:
                output_path = self._generate_output_path(resolved_path)

            result.output_path = output_path

            if self._cancelled:
                result.status = ProcessingStatus.CANCELLED
                self._set_status(ProcessingStatus.CANCELLED)
                return result

            self._set_status(ProcessingStatus.EXTRACTING_AUDIO)
            if progress_callback:
                progress_callback(ProcessingStatus.EXTRACTING_AUDIO, 0.0)

            audio_path = self._audio_extractor.extract(resolved_path)

            if progress_callback:
                progress_callback(ProcessingStatus.EXTRACTING_AUDIO, 100.0)

            if self._cancelled:
                result.status = ProcessingStatus.CANCELLED
                self._set_status(ProcessingStatus.CANCELLED)
                self._audio_extractor.cleanup()
                return result

            self._set_status(ProcessingStatus.DETECTING_SPEECH)
            if progress_callback:
                progress_callback(ProcessingStatus.DETECTING_SPEECH, 0.0)

            self._vad_detector.load_model()

            def _vad_progress(percent: float) -> None:
                if progress_callback:
                    progress_callback(ProcessingStatus.DETECTING_SPEECH, percent)

            speech_segments = self._vad_detector.detect_with_progress(
                audio_path, progress_callback=_vad_progress
            )
            result.speech_segments = speech_segments

            self._audio_extractor.cleanup()

            if self._cancelled:
                result.status = ProcessingStatus.CANCELLED
                self._set_status(ProcessingStatus.CANCELLED)
                return result

            silence_segments = VADDetector.get_silence_segments(
                speech_segments, result.original_duration
            )
            result.silence_segments = [
                _SimpleSegment(start=s[0], end=s[1]) for s in silence_segments
            ]

            if self._cancelled:
                result.status = ProcessingStatus.CANCELLED
                self._set_status(ProcessingStatus.CANCELLED)
                return result

            self._set_status(ProcessingStatus.PROCESSING_VIDEO)
            if progress_callback:
                progress_callback(ProcessingStatus.PROCESSING_VIDEO, 0.0)

            speech_as_segments = [
                Segment(start=s.start, end=s.end) for s in speech_segments
            ]

            config = ProcessingConfig(output_format=self._output_format)

            self._video_processor.remove_speech_segments(
                input_path=resolved_path,
                speech_segments=speech_as_segments,
                output_path=output_path,
                config=config,
                total_duration=result.original_duration,
            )

            if progress_callback:
                progress_callback(ProcessingStatus.PROCESSING_VIDEO, 100.0)

            if self._cancelled:
                result.status = ProcessingStatus.CANCELLED
                self._set_status(ProcessingStatus.CANCELLED)
                return result

            output_info = self._audio_extractor.get_video_info(output_path)
            result.output_duration = output_info.get("duration", 0.0)

            result.status = ProcessingStatus.COMPLETED
            self._set_status(ProcessingStatus.COMPLETED)

        except Exception as exc:
            result.status = ProcessingStatus.ERROR
            result.error_message = str(exc)
            self._set_status(ProcessingStatus.ERROR)

        return result

    def batch_process(
        self,
        video_paths: List[str],
        output_dir: Optional[str] = None,
        progress_callback: Optional[Callable[[ProcessingStatus, float], None]] = None,
    ) -> List[ProcessingResult]:
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)

        results: List[ProcessingResult] = []

        for i, video_path in enumerate(video_paths):
            if self._cancelled:
                break

            def _batch_progress(
                status: ProcessingStatus, percent: float, idx: int = i, total: int = len(video_paths)
            ) -> None:
                if progress_callback:
                    overall = (idx / total) * 100.0 + (percent / total)
                    progress_callback(status, overall)

            output_path = None
            if output_dir:
                base_name = os.path.splitext(os.path.basename(video_path))[0]
                output_filename = f"{base_name}_asmr.{self._output_format}"
                output_path = os.path.join(output_dir, output_filename)

            result = self.process(
                video_path=video_path,
                output_path=output_path,
                progress_callback=_batch_progress,
            )
            results.append(result)

        return results

    def cancel(self) -> None:
        self._cancelled = True
        self._set_status(ProcessingStatus.CANCELLED)

    def get_video_info(self, video_path: str) -> dict:
        resolved = validate_video_file(video_path)
        return self._audio_extractor.get_video_info(resolved)
