import re


def format_time(seconds: float) -> str:
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    whole_secs = int(secs)
    millis = int(round((secs - whole_secs) * 1000)) % 1000
    return f"{hours:02d}:{minutes:02d}:{whole_secs:02d}.{millis:03d}"


def format_file_size(bytes_size: int) -> str:
    if bytes_size < 0:
        return "0 B"

    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(bytes_size)
    unit_index = 0

    while size >= 1024 and unit_index < len(units) - 1:
        size /= 1024
        unit_index += 1

    if unit_index == 0:
        return f"{int(size)} {units[unit_index]}"

    return f"{size:.2f} {units[unit_index]}"


def safe_filename(name: str) -> str:
    return re.sub(r"[^\w\.\-]", "", name)


def calculate_speech_percentage(speech_segments, total_duration: float) -> float:
    if total_duration <= 0:
        return 0.0

    speech_duration = sum(seg.end - seg.start for seg in speech_segments)
    return min((speech_duration / total_duration) * 100.0, 100.0)
