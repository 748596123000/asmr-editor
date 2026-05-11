# ASMR视频自动剪辑软件 - 项目文档

## 📋 项目概述

一款专为ASMR创作者设计的智能视频剪辑工具，基于AI技术自动识别并移除视频中的说话人声，保留纯净的ASMR触发音。

---

## 🏗️ 项目结构

```
asmr-editor/
├── src/                              # 源代码目录
│   ├── __init__.py
│   ├── main.py                       # 程序入口点
│   │
│   ├── core/                         # 核心处理模块
│   │   ├── __init__.py
│   │   ├── audio_extractor.py        # 音频提取器（安全FFmpeg封装）
│   │   ├── vad_detector.py           # VAD人声检测器（模型完整性校验）
│   │   ├── video_processor.py        # 视频处理器（安全FFmpeg封装）
│   │   └── clip_engine.py            # 剪辑引擎（输入验证、流程编排）
│   │
│   ├── gui/                          # 图形界面模块
│   │   ├── __init__.py
│   │   ├── main_window.py            # 主窗口（线程安全GUI交互）
│   │   ├── timeline.py               # 时间轴组件
│   │   └── worker.py                 # 后台工作线程
│   │
│   └── utils/                        # 工具模块
│       ├── __init__.py
│       ├── config.py                 # 配置管理
│       ├── errors.py                 # 统一错误处理
│       ├── ffmpeg_runner.py          # FFmpeg安全调用封装
│       ├── helpers.py                # 辅助函数
│       ├── log_manager.py            # 安全日志管理
│       ├── temp_manager.py           # 临时文件安全管理
│       └── validators.py             # 输入验证
│
├── tests/                            # 测试目录
│   ├── __init__.py
│   ├── test_audio_extractor.py
│   ├── test_vad_detector.py
│   └── test_video_processor.py
│
├── models/                           # 预训练模型目录
│   └── silero_vad.jit
│
├── docs/                             # 文档目录
│   ├── usage.md
│   └── project_documentation.md
│
├── assets/                           # 资源文件目录
├── requirements.txt                  # 生产依赖（固定版本）
├── requirements-dev.txt              # 开发依赖（固定版本）
├── README.md
└── .gitignore
```

---

## ⚙️ 核心功能

### 1. 音频提取模块 (audio_extractor.py)

| 功能 | 说明 |
|------|------|
| `extract()` | 从视频提取16kHz单声道WAV音频 |
| `extract_to_numpy()` | 直接提取为NumPy数组 |
| `get_video_info()` | 获取视频元数据（时长、分辨率、编码等） |
| `cleanup()` | 清理临时文件 |

**技术要点：**
- 使用FFmpeg进行音频提取
- 统一转换为16kHz采样率（适合语音检测）
- 自动管理临时文件

---

### 2. 人声检测模块 (vad_detector.py)

| 功能 | 说明 |
|------|------|
| `detect()` | 检测音频中的人声段落 |
| `detect_with_progress()` | 带进度回调的检测 |
| `get_silence_segments()` | 计算要保留的非人声片段 |
| `merge_segments()` | 合并间隔较小的段落 |

**核心类：**
```python
@dataclass
class SpeechSegment:
    start: float       # 开始时间（秒）
    end: float         # 结束时间（秒）
    confidence: float  # 置信度 (0-1)
```

**技术要点：**
- 基于Silero VAD深度学习模型
- 支持GPU加速（CUDA）
- 可调节检测阈值和最小语音时长
- 分块处理大文件，避免内存溢出

---

### 3. 视频处理模块 (video_processor.py)

| 功能 | 说明 |
|------|------|
| `cut_segments()` | 根据时间段剪辑视频 |
| `remove_speech_segments()` | 移除人声片段，保留ASMR内容 |
| `preview_segment()` | 生成片段预览 |
| `get_supported_formats()` | 获取支持的输出格式 |

**核心配置：**
```python
@dataclass
class ProcessingConfig:
    output_format: str = 'mp4'      # 输出格式
    video_codec: str = 'copy'       # 视频编码（copy=无损）
    audio_codec: str = 'copy'       # 音频编码
    fade_duration: float = 0.1      # 淡入淡出时长
```

**技术要点：**
- FFmpeg无损剪辑（不重新编码）
- 智能片段合并
- 支持多种输出格式（MP4/MOV/MKV/AVI/WebM）

---

### 4. 剪辑引擎 (clip_engine.py)

| 功能 | 说明 |
|------|------|
| `process()` | 完整处理流程（提取→检测→剪辑） |
| `batch_process()` | 批量处理多个视频 |
| `get_video_info()` | 获取视频信息 |

**处理流程：**
```
视频输入 → 音频提取 → AI人声检测 → 计算保留片段 → 视频剪辑 → 输出
```

**处理状态：**
- `IDLE` - 空闲
- `EXTRACTING_AUDIO` - 提取音频
- `DETECTING_SPEECH` - 检测人声
- `PROCESSING_VIDEO` - 处理视频
- `COMPLETED` - 完成
- `ERROR` - 错误
- `CANCELLED` - 取消

---

### 5. GUI界面 (main_window.py)

| 组件 | 功能 |
|------|------|
| 文件列表 | 管理待处理视频，支持拖拽 |
| 参数面板 | 调整检测阈值、时长等参数 |
| 进度条 | 显示处理进度 |
| 日志窗口 | 显示处理日志 |
| 视频信息 | 显示视频元数据 |
| 检测结果 | 显示检测摘要 |

**快捷键：**
- `Ctrl+O` - 打开视频
- `Ctrl+Q` - 退出

---

### 6. 时间轴组件 (timeline.py)

| 功能 | 说明 |
|------|------|
| 可视化显示 | 绿色=保留片段，红色=人声片段 |
| 交互操作 | 点击跳转到指定时间 |
| 信息统计 | 显示总时长、人声时长、保留时长 |

---

## 🛠️ 技术栈

### 核心依赖

| 技术 | 版本 | 用途 |
|------|------|------|
| Python | 3.9+ | 编程语言 |
| PyQt6 | 6.4+ | GUI框架 |
| FFmpeg | 4.0+ | 视频处理 |
| ffmpeg-python | 0.2+ | FFmpeg Python绑定 |

### AI/ML依赖

| 技术 | 版本 | 用途 |
|------|------|------|
| PyTorch | 2.0+ | 深度学习框架 |
| TorchAudio | 2.0+ | 音频处理 |
| Silero VAD | - | 预训练人声检测模型 |
| ONNX Runtime | 1.15+ | 模型推理加速（可选） |

### 音频处理

| 技术 | 版本 | 用途 |
|------|------|------|
| librosa | 0.10+ | 音频特征提取 |
| pydub | 0.25+ | 音频切片处理 |
| soundfile | 0.12+ | 音频文件读写 |

### 工具库

| 技术 | 版本 | 用途 |
|------|------|------|
| NumPy | 1.24+ | 数值计算 |
| PyYAML | 6.0+ | 配置文件解析 |
| appdirs | 1.4+ | 跨平台配置目录 |
| tqdm | 4.65+ | 进度条显示 |

### 开发依赖

| 技术 | 版本 | 用途 |
|------|------|------|
| pytest | 7.3+ | 单元测试 |
| black | 23.3+ | 代码格式化 |
| pylint | 2.17+ | 代码检查 |

---

## 🔧 系统要求

### 最低配置
- **操作系统**: Windows 10 / macOS 10.15 / Linux Ubuntu 20.04
- **Python**: 3.9 或更高
- **内存**: 4GB RAM
- **存储**: 500MB 可用空间
- **FFmpeg**: 4.0 或更高版本

### 推荐配置
- **操作系统**: Windows 11 / macOS 13 / Linux Ubuntu 22.04
- **Python**: 3.11
- **内存**: 8GB+ RAM
- **显卡**: NVIDIA GPU with CUDA 11.8+
- **存储**: SSD，2GB+ 可用空间

---

## 📊 性能指标

| 指标 | 目标值 |
|------|--------|
| 人声检测准确率 | > 95% |
| 处理速度 | 0.5-1x 视频时长 |
| 内存占用 | < 2GB |
| GPU显存占用 | < 1GB |

---

## 🚀 运行方式

### 1. 安装依赖

```bash
# 创建虚拟环境
python -m venv venv

# 激活虚拟环境
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

### 2. 运行软件

```bash
python src/main.py
```

### 3. 运行测试

```bash
python -m pytest tests/
```

---

## 📦 打包发布

### 使用PyInstaller

```bash
# 安装PyInstaller
pip install pyinstaller

# 打包
pyinstaller --name "ASMR Editor" \
            --windowed \
            --icon=assets/icon.ico \
            src/main.py
```

### 使用Nuitka（推荐，性能更好）

```bash
# 安装Nuitka
pip install nuitka

# 编译
python -m nuitka --standalone \
                 --windows-disable-console \
                 --enable-plugin=pyqt6 \
                 src/main.py
```

---

## 🔐 许可证

MIT License

---

## 📞 支持与反馈

- 问题反馈: [GitHub Issues]
- 文档更新: [GitHub Wiki]
- 邮件联系: support@asmr-editor.com

---

## 🔒 安全设计

### FFmpeg 调用安全
- 所有 FFmpeg/FFprobe 调用通过 `FFmpegRunner` 封装，强制使用参数列表形式
- 严禁使用 `shell=True`，防止命令注入攻击
- 所有文件路径通过 `validate_file_path()` 校验，拒绝包含 shell 元字符和路径遍历序列的输入
- 符号链接自动解析为真实路径并重新校验

### 文件路径安全
- `validate_file_path()`: 校验输入文件路径，拒绝 shell 元字符、路径遍历、非常规文件
- `validate_output_path()`: 校验输出路径，验证父目录存在
- `validate_video_file()`: 额外验证视频格式白名单和文件大小上限（10GB）

### 临时文件安全
- 使用 `TempFileManager` 统一管理临时文件
- 通过 `tempfile.mkstemp()` 创建，权限设置为 0600（仅当前用户可读写）
- 线程安全（使用 threading.Lock）
- 支持上下文管理器自动清理
- 异常情况下确保临时文件被清理

### 模型完整性验证
- Silero VAD 模型加载前进行 SHA256 哈希校验
- 模型下载后自动验证完整性
- 校验失败时拒绝加载并提示重新下载
- 已知模型哈希值硬编码在 `KNOWN_MODEL_HASHES` 字典中

### 输入验证
- 视频格式白名单验证（mp4, avi, mkv, mov, webm, flv, wmv, ts, mts, m2ts）
- 输出格式白名单验证（mp4, mov, mkv, avi, webm）
- 检测阈值范围验证（0 < threshold < 1）
- 正数参数验证（最小语音时长等）
- 文件大小合理性检查（上限 10GB）

---

## ⚠️ 错误处理规范

### 异常层次结构
```
ASMRError (基类)
├── ProcessingError (通用处理错误)
├── AudioExtractionError (音频提取失败)
├── SpeechDetectionError (人声检测失败)
├── VideoProcessingError (视频处理失败)
├── ValidationError (输入验证失败)
├── CancellationError (处理被取消)
├── FFmpegError (FFmpeg调用错误)
│   ├── FFmpegNotFoundError (FFmpeg未安装)
│   └── InvalidPathError (路径校验失败)
└── ModelIntegrityError (模型校验失败)
```

### 用户提示策略
- 向用户显示友好的中文错误信息，不暴露内部实现细节
- 错误信息通过 `USER_MESSAGES` 字典映射，由 `get_user_message()` 获取
- FFmpeg 错误输出不直接暴露给用户

### 日志安全
- `SecureLogger` 自动对日志消息进行脱敏处理
- 用户目录路径替换为 `***`（如 `C:\Users\username` → `C:\Users\***`）
- 不记录敏感信息（完整用户目录路径等）

---

## 🧵 线程模型

### 架构设计
```
┌─────────────────────────────────┐
│         GUI 主线程 (Main Thread)  │
│  ┌───────────┐  ┌─────────────┐ │
│  │ MainWindow │  │ TimelineWidget│ │
│  └─────┬─────┘  └─────────────┘ │
│        │ 信号槽通信               │
│  ┌─────┴──────┐                  │
│  │WorkerSignals│                  │
│  └─────┬──────┘                  │
└────────┼────────────────────────┘
         │ pyqtSignal
┌────────┼────────────────────────┐
│     工作线程 (QThread)           │
│  ┌─────┴──────────────────────┐ │
│  │ ProcessingWorker /          │ │
│  │ BatchProcessingWorker       │ │
│  │  ┌──────────────────────┐  │ │
│  │  │ ClipEngine.process() │  │ │
│  │  │  ├─ AudioExtractor   │  │ │
│  │  │  ├─ VADDetector      │  │ │
│  │  │  └─ VideoProcessor   │  │ │
│  │  └──────────────────────┘  │ │
│  └────────────────────────────┘ │
└─────────────────────────────────┘
```

### 关键规则
1. **禁止跨线程操作 GUI**：工作线程不得直接调用任何 QWidget 方法
2. **信号槽通信**：所有线程间数据传递通过 Qt 信号槽机制
3. **协作式取消**：通过 `_cancelled` 标志实现，在每个处理阶段间检查
4. **安全退出**：窗口关闭时等待工作线程结束（带超时）

### Worker 信号定义
| 信号 | 参数 | 用途 |
|------|------|------|
| `finished` | ProcessingResult | 处理完成 |
| `error` | str (用户友好消息) | 处理出错 |
| `progress` | (str, float) | 进度更新（阶段名, 百分比） |
| `cancelled` | 无 | 处理被取消 |

---

## 📝 更新日志

### v1.0.0 (2024-01)
- ✨ 初始版本发布
- 🤖 集成Silero VAD人声检测
- 🎬 支持多种视频格式
- 🖥️ PyQt6现代化界面
- 📦 批量处理功能
- 📊 可视化时间轴

---

*文档版本: 1.0.0*
*最后更新: 2024-01*
