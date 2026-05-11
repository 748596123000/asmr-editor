from typing import List, Optional

from PyQt5.QtCore import QThread, QObject, pyqtSignal

from src.core.clip_engine import ClipEngine, ProcessingStatus
from src.utils.errors import CancellationError, get_user_message


class WorkerSignals(QObject):
    finished = pyqtSignal(object)
    error = pyqtSignal(str)
    progress = pyqtSignal(str, float)
    cancelled = pyqtSignal()


class ProcessingWorker(QThread):
    def __init__(
        self,
        clip_engine: ClipEngine,
        video_path: str,
        output_path: Optional[str] = None,
        parent=None,
    ):
        super().__init__(parent)
        self.clip_engine = clip_engine
        self.video_path = video_path
        self.output_path = output_path
        self.signals = WorkerSignals()

    def run(self):
        try:
            def _progress_callback(status: ProcessingStatus, percent: float):
                self.signals.progress.emit(status.value, percent)

            result = self.clip_engine.process(
                video_path=self.video_path,
                output_path=self.output_path,
                progress_callback=_progress_callback,
            )

            if result.status == ProcessingStatus.CANCELLED:
                self.signals.cancelled.emit()
            else:
                self.signals.finished.emit(result)

        except CancellationError:
            self.signals.cancelled.emit()
        except Exception as exc:
            self.signals.error.emit(get_user_message(exc))

    def cancel(self):
        self.clip_engine.cancel()


class BatchProcessingWorker(QThread):
    def __init__(
        self,
        clip_engine: ClipEngine,
        video_paths: List[str],
        output_dir: Optional[str] = None,
        parent=None,
    ):
        super().__init__(parent)
        self.clip_engine = clip_engine
        self.video_paths = video_paths
        self.output_dir = output_dir
        self.signals = WorkerSignals()

    def run(self):
        try:
            def _progress_callback(status: ProcessingStatus, percent: float):
                self.signals.progress.emit(status.value, percent)

            results = self.clip_engine.batch_process(
                video_paths=self.video_paths,
                output_dir=self.output_dir,
                progress_callback=_progress_callback,
            )

            any_cancelled = any(
                r.status == ProcessingStatus.CANCELLED for r in results
            )
            if any_cancelled:
                self.signals.cancelled.emit()
            else:
                self.signals.finished.emit(results)

        except CancellationError:
            self.signals.cancelled.emit()
        except Exception as exc:
            self.signals.error.emit(get_user_message(exc))

    def cancel(self):
        self.clip_engine.cancel()
