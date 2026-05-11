import numpy as np
import soundfile as sf
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor, QPainter, QPen
from PyQt5.QtWidgets import QWidget


def _get_start(seg):
    if hasattr(seg, "start"):
        return seg.start
    return seg[0]


def _get_end(seg):
    if hasattr(seg, "end"):
        return seg.end
    return seg[1]


class WaveformWidget(QWidget):
    position_clicked = pyqtSignal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._waveform = None
        self._sample_rate = 16000
        self._speech_segments = []
        self._silence_segments = []
        self._total_duration = 0.0
        self._playback_position = -1.0
        self.setMinimumHeight(80)
        self.setMaximumHeight(120)

    def set_waveform(self, waveform_data, sample_rate=16000):
        self._waveform = waveform_data
        self._sample_rate = sample_rate
        if waveform_data is not None:
            self._total_duration = len(waveform_data) / sample_rate
        self.update()

    def set_segments(self, speech_segments, silence_segments, total_duration=0):
        self._speech_segments = speech_segments
        self._silence_segments = silence_segments
        if total_duration > 0:
            self._total_duration = total_duration
        self.update()

    def set_playback_position(self, position):
        self._playback_position = position
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()
        margin = 10
        bar_w = w - 2 * margin
        center_y = h / 2

        painter.fillRect(self.rect(), QColor(20, 20, 30))

        if self._total_duration > 0:
            scale = bar_w / self._total_duration

            for seg in self._silence_segments:
                start = _get_start(seg)
                end = _get_end(seg)
                x = margin + start * scale
                sw = (end - start) * scale
                painter.fillRect(int(x), 0, max(int(sw), 1), h, QColor(30, 80, 30, 60))

            for seg in self._speech_segments:
                start = _get_start(seg)
                end = _get_end(seg)
                x = margin + start * scale
                sw = (end - start) * scale
                painter.fillRect(int(x), 0, max(int(sw), 1), h, QColor(80, 20, 20, 60))

        if self._waveform is not None and len(self._waveform) > 0:
            samples_per_pixel = max(1, len(self._waveform) // bar_w)
            pen = QPen(QColor(100, 180, 255, 200), 1)
            painter.setPen(pen)

            for x in range(bar_w):
                start_idx = x * samples_per_pixel
                end_idx = min(start_idx + samples_per_pixel, len(self._waveform))
                if start_idx >= len(self._waveform):
                    break
                chunk = self._waveform[start_idx:end_idx]
                if len(chunk) == 0:
                    continue
                max_val = np.max(np.abs(chunk))
                bar_height = max_val * (h / 2 - 5)
                painter.drawLine(
                    margin + x,
                    int(center_y - bar_height),
                    margin + x,
                    int(center_y + bar_height),
                )
        else:
            painter.setPen(QColor(100, 100, 100))
            painter.drawText(self.rect(), Qt.AlignCenter, "加载音频波形...")

        painter.setPen(QPen(QColor(60, 60, 80), 1))
        painter.drawLine(margin, int(center_y), margin + bar_w, int(center_y))

        if self._playback_position >= 0 and self._total_duration > 0:
            x = margin + (self._playback_position / self._total_duration) * bar_w
            painter.setPen(QPen(QColor(255, 255, 0), 2))
            painter.drawLine(int(x), 0, int(x), h)

        painter.setPen(QPen(QColor(60, 60, 80), 1))
        painter.drawRect(margin, 0, bar_w, h)

        painter.end()

    def mousePressEvent(self, event):
        if self._total_duration <= 0:
            return
        margin = 10
        bar_w = self.width() - 2 * margin
        x = event.pos().x() - margin
        if 0 <= x <= bar_w:
            time_pos = (x / bar_w) * self._total_duration
            self.position_clicked.emit(time_pos)

    def load_from_wav(self, wav_path):
        try:
            data, sr = sf.read(wav_path)
            if data.ndim > 1:
                data = np.mean(data, axis=1)
            max_val = np.max(np.abs(data))
            if max_val > 0:
                data = data / max_val
            self.set_waveform(data.astype(np.float32), sr)
        except Exception:
            self._waveform = None
            self.update()
