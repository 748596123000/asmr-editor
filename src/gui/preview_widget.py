import glob
import json
import os
import shutil
import tempfile

from PyQt5.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSlider, QVBoxLayout, QWidget

from src.utils.ffmpeg_runner import FFmpegRunner


def _get_start(seg):
    if hasattr(seg, "start"):
        return seg.start
    return seg[0]


def _get_end(seg):
    if hasattr(seg, "end"):
        return seg.end
    return seg[1]


class PreviewLoadThread(QThread):
    frames_loaded = pyqtSignal(list, float)

    def __init__(self, video_path, parent=None):
        super().__init__(parent)
        self._video_path = video_path

    def run(self):
        frames_dir = tempfile.mkdtemp(prefix="asmr_frames_")
        runner = FFmpegRunner()
        output_pattern = os.path.join(frames_dir, "frame_%04d.jpg")

        try:
            result = runner.run_ffmpeg(
                ["-i", self._video_path, "-vf", "fps=1", "-q:v", "2", output_pattern],
                input_paths=[self._video_path],
                output_paths=[output_pattern],
            )
            if not result.success:
                self.frames_loaded.emit([], 0.0)
                shutil.rmtree(frames_dir, ignore_errors=True)
                return
        except Exception:
            self.frames_loaded.emit([], 0.0)
            shutil.rmtree(frames_dir, ignore_errors=True)
            return

        frame_files = sorted(glob.glob(os.path.join(frames_dir, "frame_*.jpg")))
        frames = []
        for f in frame_files:
            img = QImage(f)
            if not img.isNull():
                frames.append(img)

        shutil.rmtree(frames_dir, ignore_errors=True)

        duration = 0.0
        try:
            probe_result = runner.run_ffprobe(
                ["-v", "quiet", "-print_format", "json", "-show_format", self._video_path],
                input_paths=[self._video_path],
            )
            if probe_result.success:
                info = json.loads(probe_result.stdout)
                duration = float(info.get("format", {}).get("duration", 0))
        except Exception:
            duration = 0.0

        self.frames_loaded.emit(frames, duration)


class VideoPreview(QWidget):
    position_changed = pyqtSignal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_frame = None
        self._duration = 0.0
        self._position = 0.0
        self._is_playing = False
        self._frames = []
        self._speech_segments = []
        self._silence_segments = []
        self._load_thread = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        self._video_label = QLabel()
        self._video_label.setMinimumSize(320, 180)
        self._video_label.setMaximumHeight(240)
        self._video_label.setAlignment(Qt.AlignCenter)
        self._video_label.setStyleSheet("background-color: #1a1a2e; border: 1px solid #333;")
        self._video_label.setText("拖入视频文件开始预览")
        layout.addWidget(self._video_label)

        seek_layout = QHBoxLayout()
        self._time_label = QLabel("00:00")
        self._seek_slider = QSlider(Qt.Horizontal)
        self._seek_slider.setRange(0, 1000)
        self._duration_label = QLabel("00:00")
        seek_layout.addWidget(self._time_label)
        seek_layout.addWidget(self._seek_slider)
        seek_layout.addWidget(self._duration_label)
        layout.addLayout(seek_layout)

        btn_layout = QHBoxLayout()
        self._play_btn = QPushButton("▶")
        self._play_btn.setFixedWidth(40)
        self._stop_btn = QPushButton("⏹")
        self._stop_btn.setFixedWidth(40)
        self._skip_speech_btn = QPushButton("跳到下一段人声")
        self._skip_silence_btn = QPushButton("跳到下一段ASMR")
        btn_layout.addWidget(self._play_btn)
        btn_layout.addWidget(self._stop_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(self._skip_speech_btn)
        btn_layout.addWidget(self._skip_silence_btn)
        layout.addLayout(btn_layout)

        self._seek_slider.sliderMoved.connect(self._on_seek)
        self._play_btn.clicked.connect(self._toggle_play)
        self._stop_btn.clicked.connect(self._stop)
        self._skip_speech_btn.clicked.connect(self._skip_to_next_speech)
        self._skip_silence_btn.clicked.connect(self._skip_to_next_silence)

        self._play_timer = QTimer()
        self._play_timer.setInterval(33)
        self._play_timer.timeout.connect(self._advance_frame)

    def load_video(self, video_path: str):
        self._frames = []
        self._duration = 0.0
        self._video_label.setText("正在加载预览...")

        if self._load_thread and self._load_thread.isRunning():
            self._load_thread.wait(2000)

        self._load_thread = PreviewLoadThread(video_path, self)
        self._load_thread.frames_loaded.connect(self._on_frames_loaded)
        self._load_thread.start()

    def _on_frames_loaded(self, frames, duration):
        self._frames = frames
        self._duration = duration

        if self._frames:
            self._show_frame(0)
        else:
            self._video_label.setText("无法加载视频预览")

        self._duration_label.setText(self._format_time(self._duration))

    def set_segments(self, speech_segments, silence_segments):
        self._speech_segments = speech_segments
        self._silence_segments = silence_segments

    def _show_frame(self, index):
        if 0 <= index < len(self._frames):
            img = self._frames[index]
            scaled = img.scaled(
                self._video_label.size(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
            self._video_label.setPixmap(QPixmap.fromImage(scaled))
            self._position = (index / max(len(self._frames) - 1, 1)) * self._duration
            self._time_label.setText(self._format_time(self._position))
            self._seek_slider.setValue(
                int((self._position / max(self._duration, 0.001)) * 1000)
            )

    def _on_seek(self, value):
        index = int((value / 1000.0) * (len(self._frames) - 1))
        self._show_frame(index)
        self._position = (value / 1000.0) * self._duration
        self.position_changed.emit(self._position)

    def _toggle_play(self):
        if self._is_playing:
            self._play_timer.stop()
            self._is_playing = False
            self._play_btn.setText("▶")
        else:
            self._play_timer.start()
            self._is_playing = True
            self._play_btn.setText("⏸")

    def _stop(self):
        self._play_timer.stop()
        self._is_playing = False
        self._play_btn.setText("▶")
        self._show_frame(0)

    def _advance_frame(self):
        current_idx = int(
            (self._position / max(self._duration, 0.001)) * (len(self._frames) - 1)
        )
        next_idx = current_idx + 1
        if next_idx >= len(self._frames):
            self._play_timer.stop()
            self._is_playing = False
            self._play_btn.setText("▶")
            return
        self._show_frame(next_idx)
        self.position_changed.emit(self._position)

    def _skip_to_next_speech(self):
        for seg in self._speech_segments:
            start = _get_start(seg)
            if start > self._position + 0.1:
                self._seek_to_time(start)
                return

    def _skip_to_next_silence(self):
        for seg in self._silence_segments:
            start = _get_start(seg)
            if start > self._position + 0.1:
                self._seek_to_time(start)
                return

    def _seek_to_time(self, time_pos):
        self._position = time_pos
        idx = int((time_pos / max(self._duration, 0.001)) * (len(self._frames) - 1))
        self._show_frame(idx)
        self.position_changed.emit(time_pos)

    @staticmethod
    def _format_time(seconds):
        m = int(seconds // 60)
        s = int(seconds % 60)
        return f"{m:02d}:{s:02d}"

    def cleanup(self):
        if self._load_thread and self._load_thread.isRunning():
            self._load_thread.wait(3000)
        self._frames = []
