from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from windows_motion_studio.models import InstalledApp, MotionProfile, PRESET_LABELS
from windows_motion_studio.profile_store import get_config_dir
from windows_motion_studio.scanner import likely_executable_path


@dataclass
class ApplyResult:
    ok: bool
    title: str
    message: str
    report_path: str = ""


def windows_animation_hint(profile: MotionProfile) -> str:
    if profile.profile == "minimal" or profile.distance <= 12:
        return "建议跟随 Windows“减少动画”偏好，仅保留透明度和状态反馈。"
    if profile.speed >= 1.2:
        return "建议缩短页面切换和浮层出现时间，优先减少等待感。"
    if profile.spring >= 55:
        return "建议仅在支持高刷新率和硬件加速的场景中启用更明显弹性。"
    return "建议使用标准 Fluent 风格过渡，保持上下文连续。"


def adapter_capability(app: InstalledApp) -> str:
    name = app.name.casefold()
    if any(token in name for token in ("visual studio code", "code")):
        return "配置可作为 VS Code 扩展或用户设置文件的输入，但 VS Code 本体不开放全局动画调速接口。"
    if any(token in name for token in ("edge", "chrome", "browser")):
        return "浏览器内部动画通常不提供公开调速接口；可通过扩展或站点级样式实现局部体验。"
    if any(token in name for token in ("photoshop", "premiere", "after effects")):
        return "创意软件动效通常由厂商内部渲染管线控制，建议通过厂商脚本/插件 SDK 做专用适配。"
    if app.app_type == "store":
        return "Store 应用受沙箱约束，优先采用系统辅助功能偏好和应用自身设置。"
    return "未发现公开动效适配器。当前仅保存配置并生成可审计策略报告。"


def build_apply_report(app: InstalledApp, profile: MotionProfile) -> dict[str, object]:
    executable = likely_executable_path(app)
    return {
        "schema": 1,
        "app": asdict(app),
        "resolved_executable": executable,
        "motion_profile": profile.to_dict(),
        "preset_label": PRESET_LABELS.get(profile.profile, "自定义"),
        "system_policy_hint": windows_animation_hint(profile),
        "adapter_capability": adapter_capability(app),
        "runtime": {
            "platform": sys.platform,
            "offline": True,
            "requires_admin": False,
            "binary_patch": False,
            "web_runtime": False,
        },
    }


def apply_profile(app: InstalledApp, profile: MotionProfile) -> ApplyResult:
    report = build_apply_report(app, profile)
    reports_dir = get_config_dir() / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    safe_name = "".join(ch if ch.isalnum() else "_" for ch in app.name)[:80].strip("_") or app.app_id
    path = reports_dir / f"{safe_name}_{app.app_id}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return ApplyResult(
        ok=True,
        title="配置已应用到本地策略库",
        message=(
            "已保存当前应用的动效配置，并生成本地适配报告。\n\n"
            "说明：该操作不会注入或修改第三方应用文件；如目标应用提供 SDK、扩展或配置接口，"
            "后续可以在 adapters 中接入专用写入逻辑。"
        ),
        report_path=str(path),
    )


def open_config_folder() -> None:
    path = get_config_dir()
    if sys.platform == "win32":
        os.startfile(path)  # type: ignore[attr-defined]
