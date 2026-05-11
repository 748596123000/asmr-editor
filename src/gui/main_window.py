import os

from PyQt5.QtCore import Qt, pyqtSignal, QObject, QThread
from PyQt5.QtGui import QFont, QPalette, QColor
from PyQt5.QtWidgets import (
    QApplication,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QSlider,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QStatusBar,
    QLineEdit,
    QSplitter,
    QInputDialog,
)

from src.core.clip_engine import ClipEngine, ProcessingResult
from src.gui.timeline import TimelineWidget
from src.gui.preview_widget import VideoPreview
from src.gui.waveform_widget import WaveformWidget
from src.gui.worker import BatchProcessingWorker, ProcessingWorker
from src.utils.log_manager import SecureLogger
from src.utils.preset_manager import PresetManager, Preset
from src.utils.project_manager import ProjectManager, ProjectData
from src.utils.temp_manager import TempFileManager
from src.utils.validators import (
    SUPPORTED_VIDEO_FORMATS,
    SUPPORTED_OUTPUT_FORMATS,
    validate_video_file,
    validate_threshold,
    validate_positive_number,
    validate_output_format,
)
from src.utils.ollama_client import OllamaClient, OllamaError, OllamaWorker


class OllamaSignals(QObject):
    response = pyqtSignal(str)
    error = pyqtSignal(str)
    models_loaded = pyqtSignal(list)
    status_checked = pyqtSignal(bool)


class OllamaCheckThread(QThread):
    def __init__(self, client, parent=None):
        super().__init__(parent)
        self.client = client
        self.signals = OllamaSignals()

    def run(self):
        try:
            available = self.client.is_available()
            self.signals.status_checked.emit(available)
            if available:
                models = self.client.list_models()
                self.signals.models_loaded.emit(models)
        except OllamaError:
            self.signals.status_checked.emit(False)


class FileLoadWorker(QThread):
    file_validated = pyqtSignal(str, str, bool)
    preview_loaded = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tasks = []
        self._running = True

    def add_file(self, filepath):
        self._tasks.append(("validate", filepath))
        if not self.isRunning():
            self.start()

    def load_preview(self, filepath):
        self._tasks.append(("preview", filepath))
        if not self.isRunning():
            self.start()

    def run(self):
        while self._running and self._tasks:
            task = self._tasks.pop(0)
            if task[0] == "validate":
                filepath = task[1]
                try:
                    validate_video_file(filepath)
                    self.file_validated.emit(filepath, "", True)
                except ValueError as e:
                    self.file_validated.emit(filepath, str(e), False)
            elif task[0] == "preview":
                filepath = task[1]
                self.preview_loaded.emit(filepath)

    def stop(self):
        self._running = False
        self.wait(2000)


class MainWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("ASMR Editor")
        self.setMinimumSize(1200, 800)

        self._clip_engine = None
        self._worker = None
        self._temp_manager = TempFileManager()
        self._secure_logger = SecureLogger("main_window")
        self._last_output_path = None

        self._ollama_client = OllamaClient()
        self._ollama_available = False
        self._chat_history = []
        self._last_result = None
        self._current_video_path = None

        self._preset_manager = PresetManager()
        self._project_manager = ProjectManager()

        self._file_loader = FileLoadWorker(self)
        self._file_loader.file_validated.connect(self._on_file_validated)
        self._file_loader.preview_loaded.connect(self._on_preview_ready)

        self._setup_ui()
        self._setup_connections()
        self._apply_dark_theme()
        self._check_ollama_status()
        self._load_presets()

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setSpacing(14)
        main_layout.setContentsMargins(16, 16, 16, 16)

        content_splitter = QSplitter(Qt.Horizontal)

        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(14)

        preview_group = QGroupBox("视频预览")
        preview_group.setFont(QFont("Microsoft YaHei", 10, QFont.Bold))
        preview_layout = QVBoxLayout(preview_group)
        preview_layout.setContentsMargins(6, 14, 6, 6)
        self._video_preview = VideoPreview()
        preview_layout.addWidget(self._video_preview)
        left_layout.addWidget(preview_group)

        file_group = QGroupBox("视频文件")
        file_group.setFont(QFont("Microsoft YaHei", 10, QFont.Bold))
        file_panel = QVBoxLayout(file_group)
        file_panel.setSpacing(8)
        file_panel.setContentsMargins(10, 14, 10, 10)
        self._file_list = QListWidget()
        self._file_list.setAcceptDrops(True)
        self._file_list.setDragDropMode(QListWidget.DropOnly)
        self._file_list.setMinimumHeight(120)
        file_panel.addWidget(self._file_list)

        file_btn_layout = QHBoxLayout()
        self._add_btn = QPushButton("添加")
        self._remove_btn = QPushButton("移除")
        self._add_btn.setToolTip("添加视频文件到处理列表")
        self._remove_btn.setToolTip("从列表中移除选中的视频文件")
        file_btn_layout.addWidget(self._add_btn)
        file_btn_layout.addWidget(self._remove_btn)
        file_panel.addLayout(file_btn_layout)

        self._load_progress = QProgressBar()
        self._load_progress.setRange(0, 0)
        self._load_progress.setValue(0)
        self._load_progress.setMaximumHeight(6)
        self._load_progress.setTextVisible(False)
        self._load_progress.hide()
        file_panel.addWidget(self._load_progress)

        left_layout.addWidget(file_group)

        content_splitter.addWidget(left_widget)

        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(14)

        param_group = QGroupBox("处理参数")
        param_group.setFont(QFont("Microsoft YaHei", 10, QFont.Bold))
        param_panel = QFormLayout(param_group)
        param_panel.setSpacing(12)
        param_panel.setContentsMargins(14, 18, 14, 14)
        param_panel.setLabelAlignment(Qt.AlignRight)

        preset_layout = QHBoxLayout()
        self._preset_combo = QComboBox()
        self._save_preset_btn = QPushButton("保存预设")
        self._delete_preset_btn = QPushButton("删除预设")
        self._save_preset_btn.setFixedWidth(80)
        self._delete_preset_btn.setFixedWidth(80)
        preset_layout.addWidget(self._preset_combo, 1)
        preset_layout.addWidget(self._save_preset_btn)
        preset_layout.addWidget(self._delete_preset_btn)
        param_panel.addRow("预设:", preset_layout)

        self._threshold_slider = QSlider(Qt.Horizontal)
        self._threshold_slider.setRange(1, 99)
        self._threshold_slider.setValue(50)
        self._threshold_label = QLabel("0.50")
        self._threshold_label.setMinimumWidth(40)
        threshold_layout = QHBoxLayout()
        threshold_layout.addWidget(self._threshold_slider)
        threshold_layout.addWidget(self._threshold_label)
        param_panel.addRow("检测阈值:", threshold_layout)

        self._min_speech_spin = QDoubleSpinBox()
        self._min_speech_spin.setRange(0.01, 10.0)
        self._min_speech_spin.setValue(0.25)
        self._min_speech_spin.setSingleStep(0.05)
        self._min_speech_spin.setDecimals(2)
        self._min_speech_spin.setSuffix(" 秒")
        param_panel.addRow("最小语音时长:", self._min_speech_spin)

        self._format_combo = QComboBox()
        self._format_combo.addItems(SUPPORTED_OUTPUT_FORMATS)
        param_panel.addRow("输出格式:", self._format_combo)

        right_layout.addWidget(param_group)

        ai_group = QGroupBox("AI 助手")
        ai_group.setFont(QFont("Microsoft YaHei", 10, QFont.Bold))
        ai_panel = QVBoxLayout(ai_group)
        ai_panel.setSpacing(8)
        ai_panel.setContentsMargins(10, 14, 10, 10)

        ai_status_layout = QHBoxLayout()
        self._ai_status_label = QLabel("状态: ● 未连接")
        self._ai_status_label.setStyleSheet("color: #ff6b6b;")
        ai_status_layout.addWidget(self._ai_status_label)
        ai_status_layout.addStretch()
        ai_panel.addLayout(ai_status_layout)

        model_layout = QHBoxLayout()
        model_layout.addWidget(QLabel("模型:"))
        self._model_combo = QComboBox()
        self._model_combo.setEditable(True)
        self._model_combo.addItem("llama3.1")
        model_layout.addWidget(self._model_combo, 1)
        ai_panel.addLayout(model_layout)

        self._chat_display = QTextEdit()
        self._chat_display.setReadOnly(True)
        self._chat_display.setMaximumHeight(200)
        self._chat_display.setPlaceholderText("AI 助手对话区域...")
        ai_panel.addWidget(self._chat_display)

        chat_input_layout = QHBoxLayout()
        self._chat_input = QLineEdit()
        self._chat_input.setPlaceholderText("输入消息...")
        self._send_btn = QPushButton("发送")
        self._send_btn.setFixedWidth(60)
        chat_input_layout.addWidget(self._chat_input)
        chat_input_layout.addWidget(self._send_btn)
        ai_panel.addLayout(chat_input_layout)

        right_layout.addWidget(ai_group, 1)

        content_splitter.addWidget(right_widget)
        content_splitter.setSizes([500, 500])

        main_layout.addWidget(content_splitter, 1)

        timeline_group = QGroupBox("时间轴")
        timeline_group.setFont(QFont("Microsoft YaHei", 10, QFont.Bold))
        timeline_layout = QVBoxLayout(timeline_group)
        timeline_layout.setContentsMargins(10, 14, 10, 10)
        timeline_layout.setSpacing(4)

        self._waveform = WaveformWidget()
        timeline_layout.addWidget(self._waveform)

        self._timeline = TimelineWidget()
        timeline_layout.addWidget(self._timeline)

        main_layout.addWidget(timeline_group, 0)

        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        main_layout.addWidget(self._progress_bar)

        log_group = QGroupBox("日志")
        log_group.setFont(QFont("Microsoft YaHei", 9, QFont.Bold))
        log_layout = QVBoxLayout(log_group)
        log_layout.setContentsMargins(8, 12, 8, 8)
        self._log_text = QTextEdit()
        self._log_text.setReadOnly(True)
        self._log_text.setMaximumHeight(120)
        log_layout.addWidget(self._log_text)
        main_layout.addWidget(log_group)

        btn_layout = QHBoxLayout()
        self._process_btn = QPushButton("开始处理")
        self._cancel_btn = QPushButton("取消")
        self._open_folder_btn = QPushButton("打开文件夹")
        self._export_project_btn = QPushButton("导出项目")
        self._import_project_btn = QPushButton("导入项目")
        self._cancel_btn.setEnabled(False)
        btn_layout.addWidget(self._process_btn)
        btn_layout.addWidget(self._cancel_btn)
        btn_layout.addWidget(self._open_folder_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(self._export_project_btn)
        btn_layout.addWidget(self._import_project_btn)
        main_layout.addLayout(btn_layout)

        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)
        self._status_bar.showMessage("就绪")

    def _setup_connections(self):
        self._add_btn.clicked.connect(self._on_add_files)
        self._remove_btn.clicked.connect(self._on_remove_files)
        self._process_btn.clicked.connect(self._on_process)
        self._cancel_btn.clicked.connect(self._on_cancel)
        self._open_folder_btn.clicked.connect(self._on_open_folder)
        self._export_project_btn.clicked.connect(self._on_export_project)
        self._import_project_btn.clicked.connect(self._on_import_project)

        self._threshold_slider.valueChanged.connect(self._on_threshold_changed)
        self._preset_combo.currentTextChanged.connect(self._on_preset_changed)
        self._save_preset_btn.clicked.connect(self._on_save_preset)
        self._delete_preset_btn.clicked.connect(self._on_delete_preset)

        self._file_list.currentRowChanged.connect(self._on_file_selected)

        self._video_preview.position_changed.connect(self._on_preview_position_changed)
        self._waveform.position_clicked.connect(self._on_waveform_position_clicked)
        self._timeline.position_clicked.connect(self._on_timeline_position_clicked)

        self._send_btn.clicked.connect(self._on_send_chat)
        self._chat_input.returnPressed.connect(self._on_send_chat)

    def _apply_dark_theme(self):
        palette = QPalette()
        palette.setColor(QPalette.Window, QColor(30, 30, 38))
        palette.setColor(QPalette.WindowText, QColor(220, 220, 230))
        palette.setColor(QPalette.Base, QColor(25, 25, 35))
        palette.setColor(QPalette.AlternateBase, QColor(35, 35, 45))
        palette.setColor(QPalette.ToolTipBase, QColor(40, 40, 50))
        palette.setColor(QPalette.ToolTipText, QColor(220, 220, 230))
        palette.setColor(QPalette.Text, QColor(220, 220, 230))
        palette.setColor(QPalette.Button, QColor(45, 45, 55))
        palette.setColor(QPalette.ButtonText, QColor(220, 220, 230))
        palette.setColor(QPalette.BrightText, QColor(255, 100, 100))
        palette.setColor(QPalette.Link, QColor(100, 150, 255))
        palette.setColor(QPalette.Highlight, QColor(80, 120, 200))
        palette.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
        palette.setColor(QPalette.Disabled, QPalette.Text, QColor(120, 120, 130))
        palette.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(120, 120, 130))
        QApplication.instance().setPalette(palette)

        self.setStyleSheet("""
            QMainWindow { background-color: #1e1e26; }
            QGroupBox {
                border: 1px solid #3a3a4a;
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 14px;
                color: #dcdce6;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 6px;
            }
            QPushButton {
                background-color: #3a3a4a;
                border: 1px solid #4a4a5a;
                border-radius: 4px;
                padding: 6px 14px;
                color: #dcdce6;
                min-height: 20px;
            }
            QPushButton:hover {
                background-color: #4a4a5a;
            }
            QPushButton:pressed {
                background-color: #2a2a3a;
            }
            QPushButton:disabled {
                background-color: #2a2a3a;
                color: #606070;
            }
            QSlider::groove:horizontal {
                height: 6px;
                background: #2a2a3a;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #6a8cd0;
                width: 16px;
                height: 16px;
                margin: -5px 0;
                border-radius: 8px;
            }
            QProgressBar {
                border: 1px solid #3a3a4a;
                border-radius: 4px;
                text-align: center;
                background-color: #2a2a3a;
                color: #dcdce6;
                min-height: 18px;
            }
            QProgressBar::chunk {
                background-color: #6a8cd0;
                border-radius: 3px;
            }
            QTextEdit, QLineEdit {
                background-color: #1e1e28;
                border: 1px solid #3a3a4a;
                border-radius: 4px;
                color: #dcdce6;
                padding: 4px;
            }
            QListWidget {
                background-color: #1e1e28;
                border: 1px solid #3a3a4a;
                border-radius: 4px;
                color: #dcdce6;
            }
            QListWidget::item:selected {
                background-color: #4a6aaa;
            }
            QComboBox {
                background-color: #2a2a3a;
                border: 1px solid #3a3a4a;
                border-radius: 4px;
                color: #dcdce6;
                padding: 4px 8px;
                min-height: 20px;
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
            QComboBox QAbstractItemView {
                background-color: #2a2a3a;
                color: #dcdce6;
                selection-background-color: #4a6aaa;
            }
            QDoubleSpinBox {
                background-color: #2a2a3a;
                border: 1px solid #3a3a4a;
                border-radius: 4px;
                color: #dcdce6;
                padding: 4px;
            }
            QStatusBar {
                background-color: #1a1a24;
                color: #9090a0;
            }
        """)

    def _check_ollama_status(self):
        self._ai_status_label.setText("状态: ● 检查中...")
        self._ai_status_label.setStyleSheet("color: #ffaa00;")
        self._ollama_check_thread = OllamaCheckThread(self._ollama_client, self)
        self._ollama_check_thread.signals.status_checked.connect(self._on_ollama_status)
        self._ollama_check_thread.signals.models_loaded.connect(self._on_ollama_models)
        self._ollama_check_thread.start()

    def _on_ollama_status(self, available):
        self._ollama_available = available
        if available:
            self._ai_status_label.setText("状态: ● 已连接")
            self._ai_status_label.setStyleSheet("color: #6bcb77;")
        else:
            self._ai_status_label.setText("状态: ● 未连接")
            self._ai_status_label.setStyleSheet("color: #ff6b6b;")

    def _on_ollama_models(self, models):
        self._model_combo.clear()
        for m in models:
            self._model_combo.addItem(m)
        if models:
            self._ollama_client.model = models[0]

    def _load_presets(self):
        self._preset_combo.blockSignals(True)
        self._preset_combo.clear()
        self._preset_combo.addItem("-- 选择预设 --")
        for preset in self._preset_manager.get_all_presets():
            self._preset_combo.addItem(preset.name)
        self._preset_combo.blockSignals(False)

    def _on_preset_changed(self, name):
        if not name or name == "-- 选择预设 --":
            return
        preset = self._preset_manager.get_preset(name)
        if preset is None:
            return
        self._threshold_slider.blockSignals(True)
        self._min_speech_spin.blockSignals(True)
        self._format_combo.blockSignals(True)

        self._threshold_slider.setValue(int(preset.vad_threshold * 100))
        self._threshold_label.setText(f"{preset.vad_threshold:.2f}")
        self._min_speech_spin.setValue(preset.min_speech_duration)

        idx = self._format_combo.findText(preset.output_format)
        if idx >= 0:
            self._format_combo.setCurrentIndex(idx)

        self._threshold_slider.blockSignals(False)
        self._min_speech_spin.blockSignals(False)
        self._format_combo.blockSignals(False)

        self._log(f"已加载预设: {name}")

    def _on_save_preset(self):
        name, ok = QInputDialog.getText(
            self, "保存预设", "预设名称:",
            text=""
        )
        if not ok or not name.strip():
            return
        name = name.strip()
        preset = Preset(
            name=name,
            vad_threshold=self._threshold_slider.value() / 100.0,
            min_speech_duration=self._min_speech_spin.value(),
            output_format=self._format_combo.currentText(),
        )
        self._preset_manager.save_preset(preset)
        self._load_presets()

        idx = self._preset_combo.findText(name)
        if idx >= 0:
            self._preset_combo.setCurrentIndex(idx)

        self._log(f"预设已保存: {name}")

    def _on_delete_preset(self):
        name = self._preset_combo.currentText()
        if not name or name == "-- 选择预设 --":
            QMessageBox.information(self, "提示", "请先选择一个预设")
            return

        result = self._preset_manager.delete_preset(name)
        if result:
            self._load_presets()
            self._preset_combo.setCurrentIndex(0)
            self._log(f"预设已删除: {name}")
        else:
            QMessageBox.warning(self, "提示", "无法删除内置预设")

    def _on_threshold_changed(self, value):
        threshold = value / 100.0
        self._threshold_label.setText(f"{threshold:.2f}")

    def _on_file_selected(self, row):
        if row < 0:
            return
        item = self._file_list.item(row)
        if item is None:
            return
        path = item.data(Qt.UserRole)
        if path and os.path.isfile(path):
            self._current_video_path = path
            self._status_bar.showMessage("正在加载视频预览...")
            self._file_loader.load_preview(path)

    def _on_preview_position_changed(self, position):
        self._waveform.set_playback_position(position)

    def _on_waveform_position_clicked(self, position):
        self._video_preview._seek_to_time(position)

    def _on_timeline_position_clicked(self, position):
        self._video_preview._seek_to_time(position)

    def _on_preview_ready(self, filepath):
        if filepath == self._current_video_path:
            self._video_preview.load_video(filepath)
            self._status_bar.showMessage("就绪")

    def _on_file_validated(self, filepath, error, is_valid):
        if not is_valid:
            QMessageBox.warning(self, "无效文件", error)
            return

        existing = set()
        for i in range(self._file_list.count()):
            existing.add(self._file_list.item(i).data(Qt.UserRole))
        if filepath in existing:
            return

        item = QListWidgetItem(os.path.basename(filepath))
        item.setData(Qt.UserRole, filepath)
        item.setToolTip(filepath)
        self._file_list.addItem(item)

        if self._file_list.count() == 1:
            self._file_list.setCurrentRow(0)
            self._current_video_path = filepath
            self._video_preview.load_video(filepath)

        self._load_progress.hide()

    def _on_add_files(self):
        filter_str = "视频文件 (" + " ".join(f"*{ext}" for ext in SUPPORTED_VIDEO_FORMATS) + ")"
        files, _ = QFileDialog.getOpenFileNames(
            self, "选择视频文件", "", filter_str
        )
        if not files:
            return

        self._load_progress.show()
        self._status_bar.showMessage(f"正在验证 {len(files)} 个文件...")

        for f in files:
            self._file_loader.add_file(f)

        self._log(f"正在添加 {len(files)} 个文件...")

    def _on_remove_files(self):
        current = self._file_list.currentRow()
        if current < 0:
            return
        self._file_list.takeItem(current)
        if self._file_list.count() == 0:
            self._current_video_path = None
        elif current < self._file_list.count():
            self._file_list.setCurrentRow(current)
        else:
            self._file_list.setCurrentRow(self._file_list.count() - 1)

    def _on_process(self):
        if self._file_list.count() == 0:
            QMessageBox.information(self, "提示", "请先添加视频文件")
            return

        threshold = self._threshold_slider.value() / 100.0
        min_speech = self._min_speech_spin.value()
        output_format = self._format_combo.currentText()

        self._clip_engine = ClipEngine(
            vad_threshold=threshold,
            min_speech_duration=min_speech,
            output_format=output_format,
        )

        video_paths = []
        for i in range(self._file_list.count()):
            path = self._file_list.item(i).data(Qt.UserRole)
            if path:
                video_paths.append(path)

        if not video_paths:
            return

        self._process_btn.setEnabled(False)
        self._cancel_btn.setEnabled(True)
        self._progress_bar.setValue(0)

        if len(video_paths) == 1:
            self._worker = ProcessingWorker(
                self._clip_engine, video_paths[0]
            )
        else:
            self._worker = BatchProcessingWorker(
                self._clip_engine, video_paths
            )

        self._worker.signals.progress.connect(self._on_progress)
        self._worker.signals.finished.connect(self._on_finished)
        self._worker.signals.error.connect(self._on_error)
        self._worker.signals.cancelled.connect(self._on_cancelled)
        self._worker.start()

        self._log("开始处理...")

    def _on_cancel(self):
        if self._worker:
            self._worker.cancel()
            self._log("正在取消...")

    def _on_progress(self, status_text, percent):
        self._progress_bar.setValue(int(percent))
        self._status_bar.showMessage(f"{status_text} - {percent:.0f}%")

        if "extracting_audio" in status_text.lower() or "提取" in status_text:
            self._log(f"音频提取中... {percent:.0f}%")
        elif "detecting" in status_text.lower() or "检测" in status_text:
            self._log(f"人声检测中... {percent:.0f}%")
        elif "processing" in status_text.lower() or "处理" in status_text:
            self._log(f"视频处理中... {percent:.0f}%")

    def _on_finished(self, result):
        self._process_btn.setEnabled(True)
        self._cancel_btn.setEnabled(False)
        self._progress_bar.setValue(100)

        if isinstance(result, list):
            self._last_result = result[-1] if result else None
            for r in result:
                if r.output_path:
                    self._last_output_path = r.output_path
        else:
            self._last_result = result
            if result.output_path:
                self._last_output_path = result.output_path

        if self._last_result:
            speech = self._last_result.speech_segments
            silence = self._last_result.silence_segments
            duration = self._last_result.original_duration

            self._timeline.set_segments(speech, silence, duration)
            self._waveform.set_segments(speech, silence, duration)
            self._video_preview.set_segments(speech, silence)

            self._log(
                f"处理完成! 原始时长: {duration:.1f}s, "
                f"人声段: {len(speech)}, 静音段: {len(silence)}"
            )

            if self._last_result.output_path:
                self._log(f"输出文件: {self._last_result.output_path}")

        self._status_bar.showMessage("处理完成")

    def _on_error(self, error_msg):
        self._process_btn.setEnabled(True)
        self._cancel_btn.setEnabled(False)
        self._progress_bar.setValue(0)
        self._log(f"错误: {error_msg}")
        QMessageBox.critical(self, "处理错误", error_msg)
        self._status_bar.showMessage("处理失败")

    def _on_cancelled(self):
        self._process_btn.setEnabled(True)
        self._cancel_btn.setEnabled(False)
        self._progress_bar.setValue(0)
        self._log("处理已取消")
        self._status_bar.showMessage("已取消")

    def _on_open_folder(self):
        if self._last_output_path and os.path.isfile(self._last_output_path):
            folder = os.path.dirname(self._last_output_path)
        else:
            folder = os.path.expanduser("~")
        os.startfile(folder)

    def _on_export_project(self):
        filepath, _ = QFileDialog.getSaveFileName(
            self, "导出项目", "",
            f"ASMR 项目文件 (*{self._project_manager.get_default_extension()})"
        )
        if not filepath:
            return
        if not filepath.endswith(self._project_manager.get_default_extension()):
            filepath += self._project_manager.get_default_extension()

        preset_name = self._preset_combo.currentText()
        if preset_name == "-- 选择预设 --":
            preset_name = ""

        data = ProjectData(
            video_path=self._current_video_path or "",
            vad_threshold=self._threshold_slider.value() / 100.0,
            min_speech_duration=self._min_speech_spin.value(),
            output_format=self._format_combo.currentText(),
            preset_name=preset_name,
        )

        if self._last_result:
            data.speech_segments = [
                {"start": s.start if hasattr(s, "start") else s[0],
                 "end": s.end if hasattr(s, "end") else s[1]}
                for s in self._last_result.speech_segments
            ]
            data.silence_segments = [
                {"start": s.start if hasattr(s, "start") else s[0],
                 "end": s.end if hasattr(s, "end") else s[1]}
                for s in self._last_result.silence_segments
            ]
            data.original_duration = self._last_result.original_duration
            data.output_path = self._last_result.output_path or ""

        try:
            self._project_manager.export_project(data, filepath)
            self._log(f"项目已导出: {filepath}")
        except Exception as e:
            QMessageBox.critical(self, "导出失败", str(e))

    def _on_import_project(self):
        filepath, _ = QFileDialog.getOpenFileName(
            self, "导入项目", "",
            f"ASMR 项目文件 (*{self._project_manager.get_default_extension()})"
        )
        if not filepath:
            return

        try:
            data = self._project_manager.import_project(filepath)
        except Exception as e:
            QMessageBox.critical(self, "导入失败", str(e))
            return

        self._threshold_slider.blockSignals(True)
        self._min_speech_spin.blockSignals(True)
        self._format_combo.blockSignals(True)

        self._threshold_slider.setValue(int(data.vad_threshold * 100))
        self._threshold_label.setText(f"{data.vad_threshold:.2f}")
        self._min_speech_spin.setValue(data.min_speech_duration)

        idx = self._format_combo.findText(data.output_format)
        if idx >= 0:
            self._format_combo.setCurrentIndex(idx)

        self._threshold_slider.blockSignals(False)
        self._min_speech_spin.blockSignals(False)
        self._format_combo.blockSignals(False)

        if data.preset_name:
            preset_idx = self._preset_combo.findText(data.preset_name)
            if preset_idx >= 0:
                self._preset_combo.setCurrentIndex(preset_idx)

        if data.video_path and os.path.isfile(data.video_path):
            self._current_video_path = data.video_path
            self._status_bar.showMessage("正在加载视频预览...")
            self._file_loader.load_preview(data.video_path)

            existing = False
            for i in range(self._file_list.count()):
                if self._file_list.item(i).data(Qt.UserRole) == data.video_path:
                    existing = True
                    break
            if not existing:
                item = QListWidgetItem(os.path.basename(data.video_path))
                item.setData(Qt.UserRole, data.video_path)
                item.setToolTip(data.video_path)
                self._file_list.addItem(item)
                self._file_list.setCurrentRow(self._file_list.count() - 1)

        if data.speech_segments or data.silence_segments:
            speech = [
                type('Seg', (), {'start': s['start'], 'end': s['end']})()
                for s in data.speech_segments
            ]
            silence = [
                type('Seg', (), {'start': s['start'], 'end': s['end']})()
                for s in data.silence_segments
            ]
            self._timeline.set_segments(speech, silence, data.original_duration)
            self._waveform.set_segments(speech, silence, data.original_duration)
            self._video_preview.set_segments(speech, silence)

        if data.output_path:
            self._last_output_path = data.output_path

        self._log(f"项目已导入: {filepath}")

    def _on_send_chat(self):
        text = self._chat_input.text().strip()
        if not text:
            return
        if not self._ollama_available:
            self._chat_display.append(
                "<span style='color: #ff6b6b;'>AI 助手未连接，请确保 Ollama 服务正在运行</span>"
            )
            return

        self._chat_display.append(f"<b>你:</b> {text}")
        self._chat_input.clear()
        self._send_btn.setEnabled(False)

        self._chat_history.append({"role": "user", "content": text})

        self._ollama_client.model = self._model_combo.currentText() or "llama3.1"

        def on_response(resp):
            self._chat_display.append(f"<b>AI:</b> {resp}")
            self._chat_history.append({"role": "assistant", "content": resp})
            self._send_btn.setEnabled(True)

        def on_error(err):
            self._chat_display.append(
                f"<span style='color: #ff6b6b;'>错误: {err}</span>"
            )
            self._send_btn.setEnabled(True)

        worker = OllamaWorker(
            client=self._ollama_client,
            mode="chat",
            callback=on_response,
            error_callback=on_error,
            messages=list(self._chat_history),
        )
        worker.start()

    def _log(self, message):
        self._log_text.append(message)
        self._log_text.verticalScrollBar().setValue(
            self._log_text.verticalScrollBar().maximum()
        )

    def closeEvent(self, event):
        self._file_loader.stop()
        self._video_preview.cleanup()
        self._temp_manager.cleanup()
        event.accept()
