from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QMouseEvent, QPainter, QColor, QPen
from PyQt5.QtWidgets import QWidget

from src.utils.helpers import format_time


def _get_start(seg):
    if hasattr(seg, "start"):
        return seg.start
    return seg[0]


def _get_end(seg):
    if hasattr(seg, "end"):
        return seg.end
    return seg[1]


class TimelineWidget(QWidget):
    position_clicked = pyqtSignal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._speech_segments = []
        self._silence_segments = []
        self._total_duration = 0.0
        self.setMinimumHeight(120)
        self.setMaximumHeight(160)

    def set_segments(self, speech_segments, silence_segments, total_duration):
        self._speech_segments = speech_segments
        self._silence_segments = silence_segments
        self._total_duration = total_duration
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()
        margin = 10
        bar_y = 24
        bar_h = h - 48
        bar_w = w - 2 * margin

        painter.fillRect(self.rect(), QColor(20, 20, 24))

        painter.setPen(QPen(QColor(60, 60, 70), 1))
        painter.setBrush(QColor(40, 40, 48))
        painter.drawRect(margin, bar_y, bar_w, bar_h)

        if self._total_duration <= 0:
            painter.setPen(QColor(120, 120, 130))
            painter.drawText(margin, bar_y + bar_h // 2 + 4, "未加载数据")
            painter.end()
            return

        scale = bar_w / self._total_duration

        for seg in self._silence_segments:
            x = margin + _get_start(seg) * scale
            sw = (_get_end(seg) - _get_start(seg)) * scale
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(76, 175, 80, 200))
            painter.drawRect(int(x), bar_y, max(int(sw), 1), bar_h)

        for seg in self._speech_segments:
            x = margin + _get_start(seg) * scale
            sw = (_get_end(seg) - _get_start(seg)) * scale
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(244, 67, 54, 200))
            painter.drawRect(int(x), bar_y, max(int(sw), 1), bar_h)

        painter.setPen(QPen(QColor(160, 160, 170), 1))
        num_labels = max(1, int(bar_w / 100))
        interval = self._total_duration / num_labels
        for i in range(num_labels + 1):
            t = i * interval
            if t > self._total_duration:
                break
            x = margin + t * scale
            painter.drawLine(int(x), bar_y + bar_h, int(x), bar_y + bar_h + 6)
            painter.drawText(int(x) - 22, bar_y + bar_h + 20, format_time(t))

        painter.end()

    def mousePressEvent(self, event: QMouseEvent):
        if self._total_duration <= 0:
            return

        margin = 10
        bar_w = self.width() - 2 * margin
        x = event.pos().x() - margin

        if 0 <= x <= bar_w:
            time_pos = (x / bar_w) * self._total_duration
            self.position_clicked.emit(time_pos)

    def get_statistics(self):
        speech_duration = sum(
            _get_end(seg) - _get_start(seg) for seg in self._speech_segments
        )
        silence_duration = sum(
            _get_end(seg) - _get_start(seg) for seg in self._silence_segments
        )
        speech_pct = 0.0
        if self._total_duration > 0:
            speech_pct = min(
                (speech_duration / self._total_duration) * 100.0, 100.0
            )
        return {
            "total_duration": self._total_duration,
            "speech_duration": speech_duration,
            "silence_duration": silence_duration,
            "speech_percentage": speech_pct,
        }
