"""Windows system (IE/Edge) proxy settings via registry."""

from __future__ import annotations

import ctypes
import json
import os
from typing import Optional

import winreg

from platform_utils import get_app_dir, legacy_data_dirs

_REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
_INTERNET_OPTION_SETTINGS_CHANGED = 39
_INTERNET_OPTION_REFRESH = 37
_WM_SETTINGCHANGE = 0x001A
_HWND_BROADCAST = 0xFFFF


BACKUP_FILENAME = "xq_quproxy_proxy_backup.json"
LEGACY_BACKUP_FILES = ("proxy_backup.json",)


def _backup_path() -> str:
    return os.path.join(get_app_dir(), BACKUP_FILENAME)


def _migrate_legacy_backup() -> None:
    dst = _backup_path()
    if os.path.exists(dst):
        return
    for base in legacy_data_dirs():
        for name in (BACKUP_FILENAME, *LEGACY_BACKUP_FILES):
            src = os.path.join(base, name)
            if os.path.exists(src):
                try:
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    os.replace(src, dst)
                except OSError:
                    import shutil
                    shutil.copy2(src, dst)
                return


def _read_reg(name: str, default=None):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _REG_PATH) as key:
            val, _ = winreg.QueryValueEx(key, name)
            return val
    except OSError:
        return default


def _write_reg(name: str, value) -> None:
    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER, _REG_PATH, 0, winreg.KEY_SET_VALUE
    ) as key:
        if isinstance(value, int):
            winreg.SetValueEx(key, name, 0, winreg.REG_DWORD, value)
        else:
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, str(value))


def _notify_proxy_change() -> None:
    try:
        wininet = ctypes.windll.Wininet
        wininet.InternetSetOptionW(0, _INTERNET_OPTION_SETTINGS_CHANGED, 0, 0)
        wininet.InternetSetOptionW(0, _INTERNET_OPTION_REFRESH, 0, 0)
    except Exception:  # noqa: BLE001
        pass
    try:
        ctypes.windll.user32.SendMessageTimeoutW(
            _HWND_BROADCAST,
            _WM_SETTINGCHANGE,
            0,
            "Internet Settings",
            0x0002,
            1000,
            None,
        )
    except Exception:  # noqa: BLE001
        pass


def read_current_proxy() -> dict:
    enable = int(_read_reg("ProxyEnable", 0) or 0)
    server = str(_read_reg("ProxyServer", "") or "")
    override = str(_read_reg("ProxyOverride", "") or "")
    return {"enable": enable, "server": server, "override": override}


def browser_proxy_supported(protocol: str) -> bool:
    """Windows system (IE/Edge) proxy only supports HTTP for reliable browser use."""
    return (protocol or "http").lower() == "http"


def browser_proxy_unsupported_reason(protocol: str) -> str:
    protocol = (protocol or "http").lower()
    if protocol in ("s5_tcp", "s5_udp"):
        return (
            "System browser proxy does not support SOCKS5 (Windows reliably supports HTTP only)."
            "Use HTTP for testing, or configure SOCKS5 manually via a browser extension."
        )
    return f"Unsupported proxy protocol: {protocol}"


def _proxy_server_string(host: str, port: int, protocol: str) -> str:
    host = (host or "").strip()
    port = int(port)
    protocol = (protocol or "http").lower()
    endpoint = f"{host}:{port}"
    return f"http={endpoint};https={endpoint}"


def set_system_proxy(host: str, port, protocol: str = "http") -> dict:
    host = (host or "").strip()
    try:
        port = int(port)
    except (TypeError, ValueError):
        return {"ok": False, "error": "Invalid port"}
    if not host:
        return {"ok": False, "error": "Proxy address is empty"}
    if not (0 < port < 65536):
        return {"ok": False, "error": "Port out of range"}
    if not browser_proxy_supported(protocol):
        return {"ok": False, "error": browser_proxy_unsupported_reason(protocol)}

    current = read_current_proxy()
    _migrate_legacy_backup()
    backup_path = _backup_path()
    if not os.path.exists(backup_path):
        with open(backup_path, "w", encoding="utf-8") as fh:
            json.dump(current, fh, ensure_ascii=False, indent=2)

    server = _proxy_server_string(host, port, protocol)
    try:
        _write_reg("ProxyEnable", 1)
        _write_reg("ProxyServer", server)
        _notify_proxy_change()
    except OSError as exc:
        return {"ok": False, "error": f"Failed to write system proxy: {exc}"}

    return {"ok": True, "server": server}


def is_system_proxy_enabled() -> bool:
    return int(read_current_proxy().get("enable", 0) or 0) == 1


def clear_system_proxy() -> dict:
    """Restore from backup if available, otherwise disable system proxy."""
    if has_proxy_backup():
        return restore_system_proxy()
    if not is_system_proxy_enabled():
        return {"ok": True}
    try:
        _write_reg("ProxyEnable", 0)
        _write_reg("ProxyServer", "")
        _notify_proxy_change()
    except OSError as exc:
        return {"ok": False, "error": f"Failed to clear proxy: {exc}"}
    return {"ok": True}


def restore_system_proxy() -> dict:
    backup_path = _backup_path()
    if not os.path.exists(backup_path):
        return {"ok": False, "error": "No proxy backup available"}

    try:
        with open(backup_path, "r", encoding="utf-8") as fh:
            backup = json.load(fh)
        _write_reg("ProxyEnable", int(backup.get("enable", 0)))
        _write_reg("ProxyServer", str(backup.get("server", "")))
        override = backup.get("override")
        if override is not None:
            _write_reg("ProxyOverride", str(override))
        _notify_proxy_change()
        os.remove(backup_path)
    except OSError as exc:
        return {"ok": False, "error": f"Failed to restore proxy: {exc}"}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}

    return {"ok": True}


def has_proxy_backup() -> bool:
    _migrate_legacy_backup()
    return os.path.exists(_backup_path())
