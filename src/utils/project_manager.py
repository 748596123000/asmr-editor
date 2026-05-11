import json
import os
from dataclasses import dataclass, asdict, field
from typing import List, Optional


@dataclass
class ProjectData:
    version: str = "1.0"
    video_path: str = ""
    vad_threshold: float = 0.5
    min_speech_duration: float = 0.25
    output_format: str = "mp4"
    fade_duration: float = 0.1
    speech_segments: list = field(default_factory=list)
    silence_segments: list = field(default_factory=list)
    original_duration: float = 0.0
    output_path: str = ""
    preset_name: str = ""


class ProjectManager:
    @staticmethod
    def export_project(data: ProjectData, filepath: str) -> None:
        d = asdict(data)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)

    @staticmethod
    def import_project(filepath: str) -> ProjectData:
        with open(filepath, "r", encoding="utf-8") as f:
            d = json.load(f)
        return ProjectData(**{k: v for k, v in d.items() if k in ProjectData.__dataclass_fields__})

    @staticmethod
    def get_default_extension() -> str:
        return ".asmrproj"
