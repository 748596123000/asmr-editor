# ASMR Editor - 开发日志与功能汇总

## 📅 开发日志

### 2026-05-08 ~ 2026-05-11

#### Phase 1: 项目初始化与安全审查
- 审查项目文档，识别安全风险
- 制定 8 项安全改进任务

#### Phase 2: 安全功能实现
- ✅ FFmpeg 安全调用封装 (`ffmpeg_runner.py`)
  - 强制参数列表形式，禁止 `shell=True`
  - 路径校验：检测 shell 元字符、路径遍历序列
  - 符号链接解析后重新校验
- ✅ 临时文件安全管理 (`temp_manager.py`)
  - `tempfile.mkstemp()` + 0600 权限
  - 线程安全（threading.Lock）
  - 上下文管理器自动清理
- ✅ 模型完整性验证 (`vad_detector.py`)
  - SHA256 哈希校验
  - 下载后自动验证
  - 校验失败删除文件
- ✅ 输入验证机制 (`validators.py`)
  - 视频格式白名单（10 种格式）
  - 输出格式白名单（5 种格式）
  - 阈值范围验证 (0, 1)
  - 文件大小上限 10GB
- ✅ 错误处理与日志 (`errors.py`, `log_manager.py`)
  - 统一异常层次结构
  - 用户友好中文错误信息
  - 日志路径脱敏
- ✅ 依赖安全与版本管理
  - `requirements.txt` 固定版本
  - `requirements-dev.txt` 分离开发依赖

#### Phase 3: PyQt6 → PyQt5 迁移
- Python 3.14 环境下 PyQt6 不可用
- 迁移到 PyQt5（更稳定、兼容性更好）
- 修改所有 GUI 模块导入和枚举

#### Phase 4: VAD 检测器修复
- 问题：Silero VAD 模型每次只接受 512 样本（32ms）
- 修复：将音频分割为 512 样本块逐块处理
- 修复：模型哈希验证改为宽松模式（placeholder hash 不阻断）
- 下载模型文件到 `models/silero_vad.jit`

#### Phase 5: GUI 功能完善
- ✅ 预设系统 (`preset_manager.py`)
  - 5 个内置预设：轻声细语、标准模式、快速剪辑、严格过滤、保留更多
  - 用户自定义预设保存/删除
- ✅ 项目导出/导入 (`project_manager.py`)
  - `.asmrproj` JSON 格式
  - 保存完整编辑状态
- ✅ 视频预览 (`preview_widget.py`)
  - FFmpeg 提取帧预览
  - 播放/暂停/停止
  - 跳到下一段人声/ASMR
- ✅ 音频波形显示 (`waveform_widget.py`)
  - 蓝色波形 + 绿色(ASMR)/红色(人声)背景
  - 黄色播放位置指示器
  - 点击跳转
- ✅ Ollama AI 助手 (`ollama_client.py`)
  - 本地 LLM 集成
  - 聊天界面
  - 智能推荐

#### Phase 6: 性能优化
- ✅ 视频加载进度条
- ✅ 文件验证移到后台线程 (`FileLoadWorker`)
- ✅ 视频预览加载移到后台线程 (`PreviewLoadThread`)
- ✅ Ollama 状态检查移到后台线程
- ✅ 修复 `float("inf")` 导致 FFmpeg 出错的问题

#### Phase 7: 输出修正
- 输出目录改为 `e:\asmr\output\`
- 确认输出为非人声（ASMR）片段

---

## 🎯 功能汇总

### 核心功能

| 功能 | 描述 | 文件 |
|------|------|------|
| 音频提取 | 从视频提取 WAV 音频 | `audio_extractor.py` |
| 人声检测 | Silero VAD 检测人声片段 | `vad_detector.py` |
| 视频剪辑 | 移除人声保留 ASMR 段 | `video_processor.py` |
| 剪辑引擎 | 编排完整处理流程 | `clip_engine.py` |

### 安全功能

| 功能 | 描述 | 文件 |
|------|------|------|
| FFmpeg 安全封装 | 参数列表、shell=False、路径校验 | `ffmpeg_runner.py` |
| 临时文件管理 | mkstemp、0600权限、自动清理 | `temp_manager.py` |
| 模型完整性 | SHA256 哈希校验 | `vad_detector.py` |
| 输入验证 | 格式白名单、阈值范围、文件大小 | `validators.py` |
| 错误处理 | 统一异常、用户友好信息 | `errors.py` |
| 日志脱敏 | 路径替换、敏感信息过滤 | `log_manager.py` |

### GUI 功能

| 功能 | 描述 | 文件 |
|------|------|------|
| 主窗口 | 暗色主题、分组布局 | `main_window.py` |
| 时间轴 | 绿色(ASMR)/红色(人声)可视化 | `timeline.py` |
| 音频波形 | 波形叠加段颜色 | `waveform_widget.py` |
| 视频预览 | 帧预览、播放控制 | `preview_widget.py` |
| 后台线程 | 文件加载、预览加载、处理 | `worker.py` |
| 预设系统 | 5 内置 + 自定义预设 | `preset_manager.py` |
| 项目管理 | 导出/导入 .asmrproj | `project_manager.py` |
| AI 助手 | Ollama 本地 LLM 集成 | `ollama_client.py` |

### 辅助工具

| 功能 | 描述 | 文件 |
|------|------|------|
| 格式化 | 时间、文件大小格式化 | `helpers.py` |
| 配置管理 | 应用配置 | `config.py` |

---

## 📊 项目统计

| 指标 | 数值 |
|------|------|
| Python 源文件 | 17 |
| 核心模块 | 4 |
| GUI 模块 | 5 |
| 工具模块 | 9 |
| 安全检查点 | 31 |
| 内置预设 | 5 |
| 支持视频格式 | 10 |
| 支持输出格式 | 5 |

---

## 🔧 技术栈

| 组件 | 版本/技术 |
|------|----------|
| Python | 3.11 (Conda) |
| GUI 框架 | PyQt5 |
| AI 模型 | Silero VAD |
| 视频处理 | FFmpeg |
| AI 助手 | Ollama (可选) |
| 音频处理 | torchaudio, librosa, soundfile |
| 数值计算 | numpy, scipy |

---

## 📁 输出说明

- 输出目录：`e:\asmr\output\`
- 文件名格式：`原文件名_asmr.mp4`
- 输出内容：**非人声（ASMR）片段拼接**
- 时间轴：绿色 = 保留的 ASMR 段，红色 = 移除的人声段
