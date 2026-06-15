from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from windows_motion_studio.models import MotionProfile


APP_DIR_NAME = "WindowsMotionStudio"


def get_config_dir() -> Path:
    root = os.environ.get("APPDATA") or str(Path.home())
    path = Path(root) / APP_DIR_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_profile_path() -> Path:
    return get_config_dir() / "profiles.json"


class ProfileStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or get_profile_path()
        self.profiles: dict[str, MotionProfile] = {}
        self.load()

    def load(self) -> None:
        if not self.path.exists():
            self.profiles = {}
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            self.profiles = {}
            return
        raw_profiles = data.get("profiles", {}) if isinstance(data, dict) else {}
        self.profiles = {
            str(app_id): MotionProfile.from_dict(profile)
            for app_id, profile in raw_profiles.items()
            if isinstance(profile, dict)
        }

    def save(self) -> None:
        payload: dict[str, Any] = {
            "schema": 1,
            "profiles": {app_id: profile.to_dict() for app_id, profile in self.profiles.items()},
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def get(self, app_id: str) -> MotionProfile:
        return self.profiles.get(app_id, MotionProfile())

    def set(self, app_id: str, profile: MotionProfile) -> None:
        self.profiles[app_id] = profile
        self.save()

    def export_to(self, path: Path) -> None:
        self.save()
        path.write_text(self.path.read_text(encoding="utf-8"), encoding="utf-8")

    def import_from(self, path: Path) -> None:
        data = json.loads(path.read_text(encoding="utf-8"))
        raw_profiles = data.get("profiles", {}) if isinstance(data, dict) else {}
        self.profiles = {
            str(app_id): MotionProfile.from_dict(profile)
            for app_id, profile in raw_profiles.items()
            if isinstance(profile, dict)
        }
        self.save()
