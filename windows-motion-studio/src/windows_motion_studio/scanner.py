from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

from windows_motion_studio.models import InstalledApp

if sys.platform == "win32":
    import winreg
else:
    winreg = None  # type: ignore[assignment]


UNINSTALL_PATHS = (
    r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
    r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
)


def stable_app_id(*parts: str) -> str:
    raw = "|".join(part.strip().lower() for part in parts if part).encode("utf-8", errors="ignore")
    return hashlib.sha1(raw).hexdigest()[:16]


def _read_reg_value(key: object, name: str) -> str:
    try:
        value, _ = winreg.QueryValueEx(key, name)  # type: ignore[union-attr]
    except OSError:
        return ""
    return str(value).strip()


def _iter_uninstall_key(root: object, path: str) -> list[InstalledApp]:
    results: list[InstalledApp] = []
    if winreg is None:
        return results

    try:
        with winreg.OpenKey(root, path) as base_key:  # type: ignore[arg-type, union-attr]
            subkey_count, _, _ = winreg.QueryInfoKey(base_key)
            for index in range(subkey_count):
                try:
                    subkey_name = winreg.EnumKey(base_key, index)
                    with winreg.OpenKey(base_key, subkey_name) as app_key:
                        name = _read_reg_value(app_key, "DisplayName")
                        if not name:
                            continue
                        system_component = _read_reg_value(app_key, "SystemComponent")
                        release_type = _read_reg_value(app_key, "ReleaseType")
                        parent_key = _read_reg_value(app_key, "ParentKeyName")
                        if system_component == "1" or parent_key:
                            continue
                        if release_type.lower() in {"hotfix", "security update", "update"}:
                            continue
                        publisher = _read_reg_value(app_key, "Publisher")
                        version = _read_reg_value(app_key, "DisplayVersion")
                        location = _read_reg_value(app_key, "InstallLocation")
                        icon = _read_reg_value(app_key, "DisplayIcon")
                        uninstall = _read_reg_value(app_key, "UninstallString")
                        app_id = stable_app_id("win32", name, publisher, location, subkey_name)
                        results.append(
                            InstalledApp(
                                app_id=app_id,
                                name=name,
                                app_type="win32",
                                publisher=publisher,
                                version=version,
                                install_location=location,
                                executable_hint=icon,
                                uninstall_string=uninstall,
                                source=f"registry:{path}",
                            )
                        )
                except OSError:
                    continue
    except OSError:
        return results
    return results


def scan_win32_apps() -> list[InstalledApp]:
    if winreg is None:
        return []
    roots = (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER)
    apps: dict[str, InstalledApp] = {}
    for root in roots:
        for path in UNINSTALL_PATHS:
            for app in _iter_uninstall_key(root, path):
                key = app.name.casefold(), app.publisher.casefold(), app.install_location.casefold()
                apps.setdefault("|".join(key), app)
    return sorted(apps.values(), key=lambda item: item.name.casefold())


def scan_store_apps(timeout_seconds: int = 8) -> list[InstalledApp]:
    if sys.platform != "win32":
        return []

    command = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        "Get-AppxPackage | Select-Object Name,Publisher,Version,InstallLocation,PackageFullName | ConvertTo-Json -Compress",
    ]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if completed.returncode != 0 or not completed.stdout.strip():
        return []

    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return []
    if isinstance(payload, dict):
        payload = [payload]

    apps: list[InstalledApp] = []
    for item in payload:
        name = str(item.get("Name", "")).strip()
        if not name:
            continue
        package = str(item.get("PackageFullName", "")).strip()
        publisher = str(item.get("Publisher", "")).strip()
        location = str(item.get("InstallLocation", "")).strip()
        version = str(item.get("Version", "")).strip()
        apps.append(
            InstalledApp(
                app_id=stable_app_id("store", package or name, publisher),
                name=name,
                app_type="store",
                publisher=publisher,
                version=version,
                install_location=location,
                executable_hint=package,
                source="appx",
            )
        )
    return sorted(apps, key=lambda item: item.name.casefold())


def scan_installed_apps(include_store: bool = True) -> list[InstalledApp]:
    apps = scan_win32_apps()
    if include_store:
        apps.extend(scan_store_apps())

    seen: set[str] = set()
    unique: list[InstalledApp] = []
    for app in apps:
        normalized = app.name.casefold(), app.app_type, app.publisher.casefold()
        key = "|".join(normalized)
        if key in seen:
            continue
        seen.add(key)
        unique.append(app)
    return sorted(unique, key=lambda item: item.name.casefold())


def likely_executable_path(app: InstalledApp) -> str:
    candidates: list[str] = []
    if app.executable_hint:
        candidates.append(app.executable_hint.split(",")[0].strip('" '))
    if app.install_location:
        root = Path(app.install_location)
        if root.exists():
            candidates.extend(str(path) for path in root.glob("*.exe"))
    for candidate in candidates:
        if candidate and candidate.lower().endswith(".exe") and Path(candidate).exists():
            return candidate
    return ""
