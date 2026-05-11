from src.utils.ffmpeg_runner import FFmpegNotFoundError
from src.core.vad_detector import ModelIntegrityError


class ASMRError(Exception):
    pass


class ProcessingError(ASMRError):
    pass


class AudioExtractionError(ASMRError):
    pass


class SpeechDetectionError(ASMRError):
    pass


class VideoProcessingError(ASMRError):
    pass


class ValidationError(ASMRError):
    pass


class CancellationError(ASMRError):
    pass


USER_MESSAGES = {
    "AudioExtractionError": "音频提取失败，请检查视频文件是否有效",
    "SpeechDetectionError": "人声检测失败，请尝试调整检测参数",
    "VideoProcessingError": "视频处理失败，请检查输出路径和磁盘空间",
    "ValidationError": "输入参数无效，请检查文件格式和参数设置",
    "CancellationError": "处理已被取消",
    "FFmpegNotFoundError": "未找到FFmpeg，请确保已安装FFmpeg并添加到系统路径",
    "ModelIntegrityError": "模型文件校验失败，请重新下载模型",
}


def get_user_message(error: Exception) -> str:
    class_name = type(error).__name__
    if class_name in USER_MESSAGES:
        return USER_MESSAGES[class_name]
    if error.__cause__ is not None:
        cause_name = type(error.__cause__).__name__
        if cause_name in USER_MESSAGES:
            return USER_MESSAGES[cause_name]
    return str(error)
