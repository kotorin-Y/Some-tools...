from __future__ import annotations

from dataclasses import dataclass
from typing import Any

try:
    import winreg
except ImportError:  # pragma: no cover
    winreg = None  # type: ignore[assignment]


DESKTOP = r"Control Panel\Desktop"
WINDOW_METRICS = r"Control Panel\Desktop\WindowMetrics"
VISUAL_EFFECTS = r"Software\Microsoft\Windows\CurrentVersion\Explorer\VisualEffects"
ADVANCED = r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced"


@dataclass
class RegistryChange:
    path: str
    name: str
    old_value: Any
    new_value: Any


@dataclass
class SystemAnimationSettings:
    min_animate: bool = True
    menu_show_delay: int = 120
    visual_fx_setting: int = 0
    taskbar_animations: bool = True


def _read_value(path: str, name: str, default: Any = None) -> Any:
    if winreg is None:
        return default
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as key:
            value, _ = winreg.QueryValueEx(key, name)
            return value
    except OSError:
        return default


def _write_value(path: str, name: str, value: Any, value_type: int) -> RegistryChange:
    if winreg is None:
        raise RuntimeError("当前系统不支持 Windows 注册表。")
    old_value = _read_value(path, name)
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, name, 0, value_type, value)
    return RegistryChange(path=path, name=name, old_value=old_value, new_value=value)


def read_system_animation_settings() -> SystemAnimationSettings:
    min_animate = str(_read_value(WINDOW_METRICS, "MinAnimate", "1")) != "0"
    raw_delay = _read_value(DESKTOP, "MenuShowDelay", "120")
    try:
        menu_delay = max(0, min(400, int(str(raw_delay))))
    except ValueError:
        menu_delay = 120
    raw_fx = _read_value(VISUAL_EFFECTS, "VisualFXSetting", 0)
    try:
        visual_fx = int(raw_fx)
    except (TypeError, ValueError):
        visual_fx = 0
    taskbar = int(_read_value(ADVANCED, "TaskbarAnimations", 1) or 0) != 0
    return SystemAnimationSettings(
        min_animate=min_animate,
        menu_show_delay=menu_delay,
        visual_fx_setting=visual_fx,
        taskbar_animations=taskbar,
    )


def apply_system_animation_settings(settings: SystemAnimationSettings) -> list[RegistryChange]:
    if winreg is None:
        raise RuntimeError("当前系统不支持 Windows 注册表。")
    changes = [
        _write_value(WINDOW_METRICS, "MinAnimate", "1" if settings.min_animate else "0", winreg.REG_SZ),
        _write_value(DESKTOP, "MenuShowDelay", str(max(0, min(400, settings.menu_show_delay))), winreg.REG_SZ),
        _write_value(VISUAL_EFFECTS, "VisualFXSetting", int(settings.visual_fx_setting), winreg.REG_DWORD),
        _write_value(ADVANCED, "TaskbarAnimations", 1 if settings.taskbar_animations else 0, winreg.REG_DWORD),
    ]
    return changes


def recommended_system_settings(profile_key: str) -> SystemAnimationSettings:
    if profile_key == "minimal":
        return SystemAnimationSettings(False, 0, 2, False)
    if profile_key == "efficient":
        return SystemAnimationSettings(True, 40, 0, True)
    if profile_key == "calm":
        return SystemAnimationSettings(True, 180, 0, True)
    if profile_key == "expressive":
        return SystemAnimationSettings(True, 120, 1, True)
    return SystemAnimationSettings(True, 120, 0, True)


def describe_visual_fx(value: int) -> str:
    return {
        0: "由 Windows 自动选择",
        1: "最佳外观",
        2: "最佳性能",
        3: "自定义",
    }.get(value, "自定义")
