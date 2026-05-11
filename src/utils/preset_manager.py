import json
import os
from dataclasses import dataclass, asdict
from typing import List, Optional
from appdirs import user_config_dir


@dataclass
class Preset:
    name: str
    vad_threshold: float
    min_speech_duration: float
    output_format: str
    fade_duration: float = 0.1


BUILTIN_PRESETS = [
    Preset("轻声细语", 0.3, 0.15, "mp4", 0.2),
    Preset("标准模式", 0.5, 0.25, "mp4", 0.1),
    Preset("快速剪辑", 0.6, 0.5, "mp4", 0.05),
    Preset("严格过滤", 0.8, 0.3, "mp4", 0.0),
    Preset("保留更多", 0.2, 0.1, "mp4", 0.3),
]


class PresetManager:
    def __init__(self):
        self._config_dir = user_config_dir("asmr-editor", "asmr")
        self._presets_file = os.path.join(self._config_dir, "presets.json")
        self._presets: List[Preset] = []
        self._load_presets()

    def _load_presets(self):
        self._presets = list(BUILTIN_PRESETS)
        if os.path.exists(self._presets_file):
            try:
                with open(self._presets_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for item in data:
                    preset = Preset(**item)
                    found = False
                    for i, p in enumerate(self._presets):
                        if p.name == preset.name:
                            self._presets[i] = preset
                            found = True
                            break
                    if not found:
                        self._presets.append(preset)
            except (json.JSONDecodeError, TypeError):
                pass

    def _save_user_presets(self):
        builtin_names = {p.name for p in BUILTIN_PRESETS}
        user_presets = [asdict(p) for p in self._presets if p.name not in builtin_names]
        for p in self._presets:
            if p.name in builtin_names:
                original = next(bp for bp in BUILTIN_PRESETS if bp.name == p.name)
                if asdict(p) != asdict(original):
                    user_presets.append(asdict(p))
        os.makedirs(self._config_dir, exist_ok=True)
        with open(self._presets_file, "w", encoding="utf-8") as f:
            json.dump(user_presets, f, ensure_ascii=False, indent=2)

    def get_all_presets(self) -> List[Preset]:
        return list(self._presets)

    def get_preset(self, name: str) -> Optional[Preset]:
        for p in self._presets:
            if p.name == name:
                return p
        return None

    def save_preset(self, preset: Preset):
        for i, p in enumerate(self._presets):
            if p.name == preset.name:
                self._presets[i] = preset
                break
        else:
            self._presets.append(preset)
        self._save_user_presets()

    def delete_preset(self, name: str) -> bool:
        builtin_names = {p.name for p in BUILTIN_PRESETS}
        if name in builtin_names:
            return False
        for i, p in enumerate(self._presets):
            if p.name == name:
                self._presets.pop(i)
                self._save_user_presets()
                return True
        return False
