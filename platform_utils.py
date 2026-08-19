"""Platform helpers shared by desktop and Android builds."""

from __future__ import annotations

import os
import sys


def is_android() -> bool:
    return "android" in sys.platform.lower()


def get_app_dir() -> str:
    """Writable app data directory (config, backups)."""
    if is_android():
        try:
            from android.storage import app_storage_path

            path = app_storage_path()
            os.makedirs(path, exist_ok=True)
            return path
        except Exception:  # noqa: BLE001
            pass
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA", "")
        if appdata:
            path = os.path.join(appdata, "Xiequ")
            os.makedirs(path, exist_ok=True)
            return path
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def legacy_data_dirs() -> list[str]:
    """Previous config locations before Windows data moved to AppData\\Xiequ."""
    dirs: list[str] = []
    if getattr(sys, "frozen", False):
        dirs.append(os.path.dirname(sys.executable))
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in dirs:
        dirs.append(here)
    return dirs


def web_dir() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    bundled = os.path.join(here, "web")
    if os.path.isdir(bundled):
        return bundled
    alt = os.path.join(get_app_dir(), "web")
    if os.path.isdir(alt):
        return alt
    return bundled
