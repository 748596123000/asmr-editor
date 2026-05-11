import os

from src.utils.ffmpeg_runner import validate_file_path


SUPPORTED_VIDEO_FORMATS = (
    '.mp4', '.avi', '.mkv', '.mov', '.webm',
    '.flv', '.wmv', '.ts', '.mts', '.m2ts',
)

SUPPORTED_OUTPUT_FORMATS = ('mp4', 'mov', 'mkv', 'avi', 'webm')

MAX_VIDEO_SIZE_BYTES = 10 * 1024 * 1024 * 1024


def validate_video_file(path: str) -> str:
    resolved = validate_file_path(path)

    ext = os.path.splitext(resolved)[1].lower()
    if ext not in SUPPORTED_VIDEO_FORMATS:
        raise ValueError(
            f"Unsupported video format: {ext!r}. "
            f"Supported formats: {', '.join(SUPPORTED_VIDEO_FORMATS)}"
        )

    file_size = os.path.getsize(resolved)
    if file_size > MAX_VIDEO_SIZE_BYTES:
        raise ValueError(
            f"File size ({file_size} bytes) exceeds maximum allowed "
            f"size ({MAX_VIDEO_SIZE_BYTES} bytes)"
        )

    return resolved


def validate_output_format(fmt: str) -> str:
    normalized = fmt.lower().lstrip('.')
    if normalized not in SUPPORTED_OUTPUT_FORMATS:
        raise ValueError(
            f"Unsupported output format: {fmt!r}. "
            f"Supported formats: {', '.join(SUPPORTED_OUTPUT_FORMATS)}"
        )
    return normalized


def validate_threshold(value) -> float:
    try:
        num = float(value)
    except (TypeError, ValueError):
        raise ValueError(
            f"Threshold must be a number, got {type(value).__name__}: {value!r}"
        )

    if not (0 < num < 1):
        raise ValueError(
            f"Threshold must be in range (0, 1) exclusive, got {num}"
        )

    return num


def validate_positive_number(value, name: str = 'value') -> float:
    try:
        num = float(value)
    except (TypeError, ValueError):
        raise ValueError(
            f"{name} must be a number, got {type(value).__name__}: {value!r}"
        )

    if num <= 0:
        raise ValueError(
            f"{name} must be a positive number, got {num}"
        )

    return num
