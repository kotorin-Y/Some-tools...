from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class InstalledApp:
    app_id: str
    name: str
    app_type: str = "win32"
    publisher: str = ""
    version: str = ""
    install_location: str = ""
    executable_hint: str = ""
    uninstall_string: str = ""
    source: str = "registry"


@dataclass
class ScenarioSettings:
    page: str = "standard"
    overlay: str = "standard"
    drag: str = "precise"
    notify: str = "standard"

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "ScenarioSettings":
        data = data or {}
        return cls(
            page=str(data.get("page", "standard")),
            overlay=str(data.get("overlay", "standard")),
            drag=str(data.get("drag", "precise")),
            notify=str(data.get("notify", "standard")),
        )


@dataclass
class MotionProfile:
    profile: str = "balanced"
    speed: float = 1.0
    spring: int = 34
    distance: int = 42
    scenario: ScenarioSettings = field(default_factory=ScenarioSettings)
    follow_windows_accessibility: bool = True
    battery_saver_fallback: bool = True
    high_refresh_enhancement: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "MotionProfile":
        data = data or {}
        return cls(
            profile=str(data.get("profile", "balanced")),
            speed=float(data.get("speed", 1.0)),
            spring=int(data.get("spring", 34)),
            distance=int(data.get("distance", 42)),
            scenario=ScenarioSettings.from_dict(data.get("scenario")),
            follow_windows_accessibility=bool(data.get("follow_windows_accessibility", True)),
            battery_saver_fallback=bool(data.get("battery_saver_fallback", True)),
            high_refresh_enhancement=bool(data.get("high_refresh_enhancement", True)),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


PRESETS: dict[str, MotionProfile] = {
    "balanced": MotionProfile("balanced", 1.0, 34, 42),
    "efficient": MotionProfile("efficient", 1.25, 18, 28),
    "calm": MotionProfile("calm", 0.82, 24, 34),
    "expressive": MotionProfile("expressive", 0.92, 66, 54),
    "minimal": MotionProfile("minimal", 1.35, 0, 8),
}


PRESET_LABELS = {
    "balanced": "均衡",
    "efficient": "高效",
    "calm": "柔和",
    "expressive": "活力",
    "minimal": "极简",
    "custom": "自定义",
}


PRESET_DESCRIPTIONS = {
    "balanced": "接近 Windows 默认节奏，适合多数办公和浏览场景。",
    "efficient": "缩短过渡和收束时间，适合高频操作工具。",
    "calm": "降低突兀位移，适合阅读、邮件和长时间使用。",
    "expressive": "增加轻微弹性和空间感，适合创意与媒体类工具。",
    "minimal": "尽量减少位移，仅保留必要反馈，适合无障碍和低性能设备。",
    "custom": "由当前速度、弹性和位移参数共同决定。",
}
