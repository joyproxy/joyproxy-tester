"""Backend API exposed to the web UI via pywebview.

Holds configuration (Windows: %APPDATA%\\Xiequ; Android: app storage),
runs single tests and the strictly-sequential batch loop.
"""

from __future__ import annotations

import json
import os
import queue
import re
import sys
import threading
import time
import webbrowser
from typing import Optional

import requests
from platform_utils import get_app_dir, is_android, legacy_data_dirs
from proxy_test import run_test, _DEF_HEADERS, _build_proxy_url
from proxy_parse import parse_proxy_input, resolve_proxy_fields
from version import __version__

if is_android():
    from system_proxy_android import (
        browser_proxy_supported,
        clear_system_proxy,
        has_proxy_backup,
        is_system_proxy_enabled,
        read_current_proxy,
        restore_system_proxy,
        set_system_proxy,
    )
else:
    from system_proxy import (
        browser_proxy_supported,
        clear_system_proxy,
        has_proxy_backup,
        is_system_proxy_enabled,
        read_current_proxy,
        restore_system_proxy,
        set_system_proxy,
    )


def app_dir() -> str:
    return get_app_dir()


CONFIG_FILENAME = "joyproxy_tester.json"
LEGACY_CONFIG_FILES = ("config.json",)


def config_path() -> str:
    return os.path.join(app_dir(), CONFIG_FILENAME)


def _migrate_legacy_config() -> None:
    dst = config_path()
    if os.path.exists(dst):
        return
    for base in legacy_data_dirs():
        for name in (CONFIG_FILENAME, *LEGACY_CONFIG_FILES):
            src = os.path.join(base, name)
            if os.path.exists(src):
                try:
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    os.replace(src, dst)
                except OSError:
                    import shutil
                    shutil.copy2(src, dst)
                return

DEFAULT_CONFIG = {
    "timeout": 10,
    "protocol": "http",
    "show_response_content": True,
    "apis": [],            # list of {"name", "url", "username", "password"}
    "extract_regex": r"\d{1,3}(?:\.\d{1,3}){3}[:\s,;]+\d{2,5}",
    "batch_count": 10,
    "batch_interval": 0,
    "batch_interval_unit": "s",
    "batch_sync_browser": False,
    "single_sync_browser": False,
    "udp_dns": "8.8.8.8",
    # Test Target & Public IP source:
    # - preset: fetch JSON and parse ip + country
    # - custom: fetch raw response and display what we got (no JSON parsing)
    "geo_channel": "ipinfo",
    "geo_custom_url": "",
}

_INTERVAL_UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400}
_MIN_INTERVAL_SECONDS = 10
_MAX_INTERVAL_SECONDS = 365 * 86400

# regex that pulls host (ip or domain) + port out of arbitrary api text
_HOST_PART = (
    r"(?:\d{1,3}(?:\.\d{1,3}){3}"
    r"|[a-zA-Z0-9](?:[a-zA-Z0-9\-]*\.)+[a-zA-Z]{2,})"
)
_HOSTPORT_RE = re.compile(rf"({_HOST_PART})\D{{1,3}}(\d{{2,5}})")
_IPPORT_RE = _HOSTPORT_RE  # legacy alias
_RAW_PREVIEW = 500


def _valid_port(port: int) -> bool:
    return 0 < port < 65536


def extract_all_host_ports(text: str, regex: Optional[str] = None) -> list[tuple[str, int]]:
    """Return all (host, port) pairs found in API response text."""
    text = (text or "").strip()
    if not text:
        return []
    found: list[tuple[str, int]] = []
    seen: set[tuple[str, int]] = set()

    def _add(host: str, port_s: str) -> None:
        try:
            port = int(port_s)
        except (TypeError, ValueError):
            return
        if not _valid_port(port):
            return
        host = (host or "").strip()
        if not host:
            return
        key = (host.lower(), port)
        if key in seen:
            return
        seen.add(key)
        found.append((host, port))

    if regex:
        try:
            for m in re.finditer(regex, text):
                groups = m.groups()
                if len(groups) >= 2:
                    _add(str(groups[0]), str(groups[1]))
                else:
                    m2 = _HOSTPORT_RE.search(m.group(0))
                    if m2:
                        _add(m2.group(1), m2.group(2))
        except re.error:
            pass
        if found:
            return found

    for m in _HOSTPORT_RE.finditer(text):
        _add(m.group(1), m.group(2))
    return found


def parse_api_response(text: str, regex: Optional[str] = None) -> dict:
    """Validate API text and extract the first host:port (and optional credentials)."""
    text = (text or "").strip()
    if not text:
        return {"ok": False, "error": "API response is empty", "raw": ""}

    as_proxy = parse_proxy_input(text)
    if as_proxy and as_proxy.get("host"):
        out: dict = {
            "ok": True,
            "host": as_proxy["host"],
            "port": as_proxy["port"],
            "raw": text[:_RAW_PREVIEW],
        }
        if as_proxy.get("username"):
            out["username"] = as_proxy["username"]
        if as_proxy.get("password"):
            out["password"] = as_proxy["password"]
        return out

    matches = extract_all_host_ports(text, regex)
    if not matches:
        raw = text[:_RAW_PREVIEW]
        return {
            "ok": False,
            "error": "Response is not a valid host:port or domain:port format",
            "raw": raw,
        }
    host, port = matches[0]
    out: dict = {"ok": True, "host": host, "port": port, "raw": text[:_RAW_PREVIEW]}
    if len(matches) > 1:
        out["multiple"] = True
        out["hint"] = f"Detected {len(matches)} proxy records; only the first one is used per run."
    return out


def extract_ip_port(text: str, regex: Optional[str] = None) -> Optional[tuple]:
    """Extract a single (host, port) from API response text."""
    parsed = parse_api_response(text, regex)
    if not parsed.get("ok"):
        return None
    return parsed["host"], parsed["port"]


def _normalize_apis(apis: list) -> list:
    out = []
    for item in apis or []:
        if not isinstance(item, dict):
            continue
        out.append({
            "name": str(item.get("name", "Unnamed API")),
            "url": str(item.get("url", "")),
            "username": str(item.get("username", "") or ""),
            "password": str(item.get("password", "") or ""),
        })
    return out


def _load_config() -> dict:
    _migrate_legacy_config()
    cfg = dict(DEFAULT_CONFIG)
    path = config_path()
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as fh:
                saved = json.load(fh)
            cfg.update({k: saved[k] for k in saved if k in DEFAULT_CONFIG})
            if "show_response_content" in saved:
                cfg["show_response_content"] = bool(saved["show_response_content"])
            cfg["apis"] = _normalize_apis(cfg.get("apis", []))
            # Migrate legacy or removed preset channels (e.g. ipapi.co)
            if cfg.get("geo_channel") in ("ipapi", "", None):
                cfg["geo_channel"] = DEFAULT_PRESET_KEY
    except Exception:  # noqa: BLE001
        pass
    return cfg


def _save_config(cfg: dict) -> None:
    merged = dict(DEFAULT_CONFIG)
    merged.update({k: cfg[k] for k in cfg if k in DEFAULT_CONFIG})
    merged["apis"] = _normalize_apis(merged.get("apis", []))
    with open(config_path(), "w", encoding="utf-8") as fh:
        json.dump(merged, fh, ensure_ascii=False, indent=2)


def _restore_before_extract() -> None:
    """Restore system browser proxy so API extraction uses a direct connection."""
    if is_android():
        return
    if has_proxy_backup():
        restore_system_proxy()
    elif is_system_proxy_enabled():
        clear_system_proxy()


def _proxy_scheme(protocol: str) -> str:
    protocol = (protocol or "http").lower()
    if protocol in ("s5_tcp", "s5_udp"):
        return "socks5h"
    return "http"


GEO_PRESETS = {
    # 1. ipinfo.io: returns {"ip": "...", "country": "US", ...}
    "ipinfo": {
        "name": "ipinfo.io",
        "url": "https://ipinfo.io/json",
        "ip_key": "ip",
        "country_key": "country",
    },
    # 2. ipwhois.app: returns {"ip": "...", "country": "United States", ...}
    "ipwhois": {
        "name": "ipwhois.app",
        "url": "https://ipwhois.app/json/",
        "ip_key": "ip",
        "country_key": "country",
    },
    # 3. ip-api.com: returns {"query": "...", "country": "United States", ...}
    "ip-api": {
        "name": "ip-api.com",
        "url": "http://ip-api.com/json/",
        "ip_key": "query",
        "country_key": "country",
    },
    # 4. api.myip.com: returns {"ip": "...", "country": "United States", ...}
    "myip": {
        "name": "api.myip.com",
        "url": "https://api.myip.com",
        "ip_key": "ip",
        "country_key": "country",
    },
}
DEFAULT_PRESET_KEY = "ipinfo"


def _resolve_test_target(target: str = "") -> str:
    """Return target URL for proxy connectivity tests.

    Priority: caller-provided target -> selected preset or custom channel -> default preset url.
    """
    t = (target or "").strip()
    if t:
        return t
    cfg = _load_config()
    geo_channel = str(cfg.get("geo_channel") or DEFAULT_PRESET_KEY).strip()
    if geo_channel == "custom":
        custom_url = str(cfg.get("geo_custom_url") or "").strip()
        if custom_url:
            return custom_url
        return GEO_PRESETS[DEFAULT_PRESET_KEY]["url"]
    preset = GEO_PRESETS.get(geo_channel) or GEO_PRESETS[DEFAULT_PRESET_KEY]
    return preset["url"]


def fetch_public_ip(
    target: str = "",
    timeout: float = 10,
    proxy_host: str = "",
    proxy_port=None,
    proxy_protocol: str = "http",
    proxy_username: str = "",
    proxy_password: str = "",
) -> dict:
    """Fetch current public IP + country from the configured preset or custom target URL."""
    _cfg = _load_config()
    geo_channel = str(_cfg.get("geo_channel") or DEFAULT_PRESET_KEY).strip()
    geo_custom_url = str(_cfg.get("geo_custom_url") or "").strip()

    try:
        timeout = float(timeout)
    except (TypeError, ValueError):
        timeout = 10.0

    proxies = None
    host = (proxy_host or "").strip()
    if host and proxy_port is not None:
        try:
            port = int(proxy_port)
        except (TypeError, ValueError):
            return {"ok": False, "error": "Proxy port is invalid"}
        scheme = _proxy_scheme(proxy_protocol)
        proxy_url = _build_proxy_url(
            scheme, host, port, proxy_username, proxy_password,
        )
        proxies = {"http": proxy_url, "https": proxy_url}

    # Determine URL and preset mode
    if geo_channel == "custom":
        url = (target or "").strip() or geo_custom_url
        if not url:
            return {"ok": False, "error": "Custom target URL is empty"}
        preset = None
    else:
        preset = GEO_PRESETS.get(geo_channel) or GEO_PRESETS[DEFAULT_PRESET_KEY]
        url = (target or "").strip() or preset["url"]

    try:
        resp = requests.get(
            url,
            timeout=timeout,
            headers=_DEF_HEADERS,
            verify=False,
            proxies=proxies,
        )

        if not resp.ok:
            preview = (resp.text or "").strip()[:200]
            return {"ok": False, "error": f"Request failed: HTTP {resp.status_code} {preview}"}

        # Custom: no JSON parsing; show raw response (truncated)
        if preset is None:
            text = (resp.text or "").strip()
            if len(text) > 500:
                text = text[:500] + "..."
            return {
                "ok": True,
                "ip": text,
                "country": "",
                "country_code": "",
                "content": text,
                "status": resp.status_code,
            }

        # Preset: parse JSON and extract ip + country
        geo_data = resp.json() if resp.text else {}
        ip = str(geo_data.get(preset["ip_key"], "") or "").strip()
        country = str(geo_data.get(preset["country_key"], "") or "").strip()

        # Fallback to common fields if specific key is absent
        if not ip:
            ip = str(geo_data.get("ip") or geo_data.get("query") or geo_data.get("ipAddress") or "").strip()
        if not country:
            country = str(geo_data.get("country") or geo_data.get("country_name") or geo_data.get("countryName") or "").strip()

        if not ip:
            return {"ok": False, "error": f"JSON missing IP field from {url}"}

        return {
            "ok": True,
            "ip": ip,
            "country": country,
            "country_code": str(geo_data.get("country_code") or geo_data.get("countryCode") or "").strip(),
            "content": resp.text if len(resp.text) <= 500 else (resp.text[:500] + "..."),
            "status": resp.status_code,
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


def _format_public_ip_display(ip: str, country: str = "") -> str:
    ip = (ip or "").strip()
    country = (country or "").strip()
    if ip and country:
        return f"{ip} - {country}"
    return ip or "-"


def _parse_and_format_test_result(
    result_content: str,
    protocol: str = "http",
    status: Optional[int] = None,
    geo_channel: str = "",
) -> dict:
    """Parse and format proxy connectivity test results for UI display."""
    text = (result_content or "").strip()
    proto = (protocol or "http").lower()

    if proto == "s5_udp":
        return {
            "content": text or "SOCKS5 UDP connection verified",
            "note": "UDP Connected",
            "ip": "",
            "country": "",
        }

    if not text:
        note = f"HTTP {status}" if status is not None else "Connected"
        return {
            "content": note,
            "note": note,
            "ip": "",
            "country": "",
        }

    if geo_channel == "custom":
        preview = text if len(text) <= 500 else (text[:500] + "...")
        first_line = text.splitlines()[0].strip() if text.splitlines() else text
        note = first_line[:60] if first_line else (f"HTTP {status}" if status is not None else "Connected")
        return {
            "content": preview,
            "note": note,
            "ip": "",
            "country": "",
        }

    preset = GEO_PRESETS.get(geo_channel) or GEO_PRESETS.get(DEFAULT_PRESET_KEY)
    try:
        geo_data = json.loads(text)
        ip = str(geo_data.get(preset["ip_key"] if preset else "ip", "") or "").strip()
        country = str(geo_data.get(preset["country_key"] if preset else "country", "") or "").strip()
        if not ip:
            ip = str(geo_data.get("ip") or geo_data.get("query") or geo_data.get("ipAddress") or "").strip()
        if not country:
            country = str(geo_data.get("country") or geo_data.get("country_name") or geo_data.get("countryName") or "").strip()

        if ip:
            ip_display = _format_public_ip_display(ip, country)
            try:
                pretty_json = json.dumps(geo_data, indent=2, ensure_ascii=False)
            except Exception:
                pretty_json = text
            single_content = f"{ip_display}\n\n{pretty_json}"
            return {
                "content": single_content,
                "note": ip_display,
                "ip": ip,
                "country": country,
            }
    except Exception:
        pass

    preview = text if len(text) <= 500 else (text[:500] + "...")
    first_line = text.splitlines()[0].strip() if text.splitlines() else text
    note = first_line[:60] if first_line else (f"HTTP {status}" if status is not None else "Connected")
    return {
        "content": preview,
        "note": note,
        "ip": "",
        "country": "",
    }


def _build_test_note(result, show_content: bool, proxy_note: str = "") -> str:
    if result.ok:
        content = result.content if show_content else ""
        if show_content and content:
            note = content
        elif result.status is not None:
            note = f"HTTP {result.status}"
        else:
            note = "Connected"
    else:
        note = result.error or ""
    if proxy_note:
        note = (note + " · " + proxy_note) if note else proxy_note
    return note


def fetch_proxy_from_api(api_url: str, regex: str, timeout: float) -> dict:
    """Extract one proxy endpoint from an API response."""
    _restore_before_extract()
    try:
        resp = requests.get(api_url, timeout=timeout, headers=_DEF_HEADERS, verify=False)
        parsed = parse_api_response(resp.text, regex)
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "stage": "fetch",
            "fatal": False,
            "error": f"API extraction failed: {exc}",
        }

    if not parsed.get("ok"):
        raw = parsed.get("raw", resp.text[:_RAW_PREVIEW])
        err = parsed.get("error", "Unable to parse proxy address")
        msg = f"{err}\n\nResponse content:\n{raw}"
        return {
            "ok": False,
            "stage": "parse",
            "fatal": True,
            "error": msg,
            "raw": raw,
        }

    return {
        "ok": True,
        "stage": "fetch",
        "fatal": False,
        "host": parsed["host"],
        "port": parsed["port"],
        "multiple": bool(parsed.get("multiple")),
        "hint": parsed.get("hint", ""),
    }


def test_proxy_cycle(
    host: str,
    port,
    protocol: str,
    target: str,
    timeout: float,
    dns_server: str,
    username: str,
    password: str,
    show_content: bool,
    sync_browser: bool,
) -> dict:
    """Run connectivity test (and optional browser proxy sync) for one proxy."""
    if is_android():
        sync_browser = False
    proxy_note = ""
    proxy_set_ok = False

    cfg = _load_config()
    geo_channel = str(cfg.get("geo_channel") or DEFAULT_PRESET_KEY).strip()
    resolved_target = _resolve_test_target(target)
    result = run_test(
        host, port, protocol, resolved_target, timeout,
        dns_server=dns_server,
        username=username,
        password=password,
        fetch_content=True,
    )

    if result.ok:
        parsed_res = _parse_and_format_test_result(
            result.content, protocol, result.status, geo_channel
        )
        content = parsed_res["content"]
        note = parsed_res["note"]
        parsed_ip = parsed_res.get("ip", "")
        parsed_country = parsed_res.get("country", "")
    else:
        content = result.error or "Unknown error"
        note = result.error or "Failed"
        parsed_ip = ""
        parsed_country = ""

    if sync_browser and result.ok:
        proxy_r = set_system_proxy(host, port, protocol)
        if proxy_r.get("ok"):
            proxy_set_ok = True
            proxy_note = "Browser proxy synced"
        else:
            proxy_note = "Failed to set browser proxy: " + (proxy_r.get("error") or "Unknown error")

    if proxy_note:
        note = (note + " · " + proxy_note) if note else proxy_note

    out = {
        "ok": result.ok,
        "stage": "test",
        "fatal": False,
        "elapsed_ms": result.elapsed_ms,
        "status": result.status,
        "content": content,
        "error": result.error,
        "note": note,
        "proxy_note": proxy_note,
        "ip": parsed_ip,
        "country": parsed_country,
    }
    if sync_browser and proxy_set_ok:
        ip_r = fetch_public_ip(
            resolved_target, timeout,
            proxy_host=host, proxy_port=port, proxy_protocol=protocol,
            proxy_username=username, proxy_password=password,
        )
        if ip_r.get("ok"):
            out["public_ip"] = _format_public_ip_display(
                ip_r.get("ip", ""), ip_r.get("country", ""),
            )
    return out


def execute_batch_cycle(
    api_url: str,
    protocol: str,
    target: str,
    regex: str,
    timeout: float,
    dns_server: str,
    username: str,
    password: str,
    show_content: bool,
    sync_browser: bool,
) -> dict:
    """Run one API extract (+ optional browser proxy sync) + connectivity test."""
    fetched = fetch_proxy_from_api(api_url, regex, timeout)
    if not fetched.get("ok"):
        return fetched

    host, port = fetched["host"], fetched["port"]
    user = (username or "").strip()
    pwd = password or ""
    if not user and fetched.get("username"):
        user = str(fetched.get("username") or "").strip()
    if not pwd and fetched.get("password"):
        pwd = str(fetched.get("password") or "")
    tested = test_proxy_cycle(
        host, port, protocol, target, timeout,
        dns_server=dns_server,
        username=user,
        password=pwd,
        show_content=show_content,
        sync_browser=sync_browser,
    )
    return {**fetched, **tested, "host": host, "port": port}


def validate_target_url(url: str) -> dict:
    url = (url or "").strip()
    if not url:
        return {"ok": False, "error": "Please provide a test target URL"}
    low = url.lower()
    if not (low.startswith("http://") or low.startswith("https://")):
        return {"ok": False, "error": "Test target URL must start with http:// or https://"}
    return {"ok": True, "url": url}


def parse_batch_interval(value, unit: str = "s") -> dict:
    """Convert interval value + unit to seconds. Zero means no interval."""
    try:
        num = float(value)
    except (TypeError, ValueError):
        num = 0.0
    if num <= 0:
        return {"ok": True, "seconds": 0.0, "unlimited": False}
    key = (unit or "s").lower()
    if key not in _INTERVAL_UNITS:
        return {"ok": False, "error": "Invalid interval unit"}
    seconds = num * _INTERVAL_UNITS[key]
    if seconds < _MIN_INTERVAL_SECONDS:
        return {"ok": False, "error": "Minimum interval is 10 seconds"}
    if seconds > _MAX_INTERVAL_SECONDS:
        return {"ok": False, "error": "Maximum interval is 365 days"}
    return {"ok": True, "seconds": seconds, "unlimited": True}


class Api:
    """Object exposed to JavaScript through pywebview's js_api."""

    def __init__(self) -> None:
        self._window = None
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._event_subscribers: list[queue.Queue] = []
        self._sub_lock = threading.Lock()

    def subscribe_events(self) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=256)
        with self._sub_lock:
            self._event_subscribers.append(q)
        return q

    def unsubscribe_events(self, q: queue.Queue) -> None:
        with self._sub_lock:
            if q in self._event_subscribers:
                self._event_subscribers.remove(q)

    def set_window(self, window) -> None:
        self._window = window

    # ----- config ----------------------------------------------------- #
    def get_config(self) -> dict:
        return _load_config()

    def get_version(self) -> dict:
        return {"ok": True, "version": __version__}

    def save_config(self, cfg: dict) -> dict:
        try:
            _save_config(cfg)
            return {"ok": True}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}

    def open_url(self, url: str = "https://www.joyproxy.com/") -> dict:
        target = url or "https://www.joyproxy.com/"
        if is_android():
            try:
                from jnius import autoclass

                Intent = autoclass("android.content.Intent")
                Uri = autoclass("android.net.Uri")
                PythonActivity = autoclass("org.kivy.android.PythonActivity")
                intent = Intent(Intent.ACTION_VIEW, Uri.parse(target))
                PythonActivity.mActivity.startActivity(intent)
                return {"ok": True}
            except Exception as exc:  # noqa: BLE001
                return {"ok": False, "error": str(exc)}
        try:
            webbrowser.open(target)
            return {"ok": True}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}

    def browser_proxy_supported(self, protocol: str = "http") -> dict:
        return {"ok": True, "supported": browser_proxy_supported(protocol)}

    def set_system_proxy(self, host: str, port, protocol: str = "http") -> dict:
        return set_system_proxy(host, port, protocol)

    def restore_system_proxy(self) -> dict:
        return restore_system_proxy()

    def has_proxy_backup(self) -> bool:
        return has_proxy_backup()

    def get_system_proxy_status(self) -> dict:
        current = read_current_proxy()
        return {
            "ok": True,
            "enabled": is_system_proxy_enabled(),
            "server": str(current.get("server", "") or ""),
        }

    def clear_system_proxy(self) -> dict:
        return clear_system_proxy()

    def fetch_public_ip(self, target: str = "", timeout=10,
                        proxy_host: str = "", proxy_port=None,
                        proxy_protocol: str = "http",
                        proxy_username: str = "", proxy_password: str = "") -> dict:
        return fetch_public_ip(
            target, timeout,
            proxy_host=proxy_host, proxy_port=proxy_port,
            proxy_protocol=proxy_protocol,
            proxy_username=proxy_username, proxy_password=proxy_password,
        )

    # ----- single test ------------------------------------------------ #
    def test_single(self, host: str, port, protocol: str, target: str, timeout,
                    dns_server: str = "", username: str = "", password: str = "",
                    show_content: bool = True, sync_browser: bool = False) -> dict:
        try:
            timeout = float(timeout)
        except (TypeError, ValueError):
            timeout = 10.0
        cfg = _load_config()
        dns = (dns_server or "").strip() or cfg.get("udp_dns", "8.8.8.8")
        resolved_target = _resolve_test_target(target)
        host, port_i, user, pwd, parsed_proto, was_parsed = resolve_proxy_fields(
            host, port, username, password, protocol,
        )
        if not (0 < port_i < 65536):
            return {
                "ok": False,
                "elapsed_ms": 0,
                "content": "Invalid port",
                "note": "Invalid port",
                "error": "Invalid port",
            }
        ui_proto = (protocol or "").strip()
        if was_parsed and parsed_proto:
            proto = parsed_proto
        else:
            proto = ui_proto or parsed_proto or "http"
        geo_channel = str(cfg.get("geo_channel") or DEFAULT_PRESET_KEY).strip()

        result = run_test(host, port_i, proto, resolved_target, timeout, dns_server=dns,
                          username=user, password=pwd, fetch_content=True)
        data = result.to_dict()

        if result.ok:
            parsed_res = _parse_and_format_test_result(
                result.content, protocol, result.status, geo_channel
            )
            data["content"] = parsed_res["content"]
            data["note"] = parsed_res["note"]
            if parsed_res.get("ip"):
                data["ip"] = parsed_res["ip"]
                data["country"] = parsed_res.get("country", "")
        else:
            data["content"] = result.error or "Unknown error"
            data["note"] = result.error or "Failed"

        proxy_note = ""
        if sync_browser and result.ok:
            proxy_r = set_system_proxy(host, port_i, proto)
            if proxy_r.get("ok"):
                proxy_note = "Browser proxy synced"
                ip_r = fetch_public_ip(
                    resolved_target, timeout,
                    proxy_host=host, proxy_port=port_i, proxy_protocol=proto,
                    proxy_username=user, proxy_password=pwd,
                )
                if ip_r.get("ok"):
                    data["public_ip"] = _format_public_ip_display(
                        ip_r.get("ip", ""), ip_r.get("country", ""),
                    )
            else:
                proxy_note = "Failed to set browser proxy: " + (proxy_r.get("error") or "Unknown error")
        if proxy_note:
            data["proxy_note"] = proxy_note
            if data.get("note"):
                data["note"] += f" · {proxy_note}"
            else:
                data["note"] = proxy_note
        return data

    # ----- api extraction (one ip) ------------------------------------ #
    def fetch_one(self, api_url: str, regex: str = "", timeout=10) -> dict:
        try:
            timeout = float(timeout)
        except (TypeError, ValueError):
            timeout = 10.0
        _restore_before_extract()
        try:
            resp = requests.get(api_url, timeout=timeout, headers=_DEF_HEADERS, verify=False)
            text = resp.text
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"Extraction failed: {exc}"}
        parsed = parse_api_response(text, regex)
        if not parsed.get("ok"):
            raw = parsed.get("raw", "")
            err = parsed.get("error", "Unable to parse proxy address")
            if raw:
                err = f"{err}\n\nResponse content:\n{raw}"
            return {"ok": False, "error": err, "raw": raw}
        return parsed

    def test_extracted_proxy(self, params: dict) -> dict:
        try:
            timeout = float(params.get("timeout", 10))
        except (TypeError, ValueError):
            timeout = 10.0
        dns_server = (params.get("dns_server") or "").strip() or _load_config().get("udp_dns", "8.8.8.8")
        return test_proxy_cycle(
            params.get("host", ""),
            params.get("port"),
            params.get("protocol", "http"),
            params.get("target", ""),
            timeout,
            dns_server,
            (params.get("username") or "").strip(),
            params.get("password") or "",
            bool(params.get("show_response_content", True)),
            bool(params.get("sync_browser")),
        )

    def run_batch_once(self, params: dict) -> dict:
        if self._thread and self._thread.is_alive():
            return {"ok": False, "error": "A batch task is running; please stop it first"}
        try:
            timeout = float(params.get("timeout", 10))
        except (TypeError, ValueError):
            timeout = 10.0
        dns_server = (params.get("dns_server") or "").strip() or _load_config().get("udp_dns", "8.8.8.8")
        result = execute_batch_cycle(
            api_url=params.get("api_url", ""),
            protocol=params.get("protocol", "http"),
            target=params.get("target", ""),
            regex=params.get("regex", ""),
            timeout=timeout,
            dns_server=dns_server,
            username=(params.get("username") or "").strip(),
            password=params.get("password") or "",
            show_content=bool(params.get("show_response_content", True)),
            sync_browser=bool(params.get("sync_browser")),
        )
        return result

    # ----- sequential batch ------------------------------------------- #
    def start_batch(self, params: dict) -> dict:
        if self._thread and self._thread.is_alive():
            return {"ok": False, "error": "A task is already running"}
        interval_info = parse_batch_interval(
            params.get("interval", 0),
            params.get("interval_unit", "s"),
        )
        if not interval_info.get("ok"):
            return {"ok": False, "error": interval_info.get("error", "Invalid interval parameters")}
        self._stop.clear()
        self._thread = threading.Thread(target=self._run_batch, args=(params,), daemon=True)
        self._thread.start()
        return {"ok": True}

    def stop_batch(self) -> dict:
        self._stop.set()
        return {"ok": True}

    def _wait_interval(self, seconds: float, index: int = 0) -> bool:
        """Wait up to *seconds*, emitting countdown ticks. Returns False if stopped."""
        if seconds <= 0:
            return True
        end = time.monotonic() + seconds
        last_shown = -1
        total = int(seconds)
        while True:
            if self._stop.is_set():
                self._emit({"type": "countdown_done", "index": index})
                return False
            remain = end - time.monotonic()
            if remain <= 0:
                break
            remain_sec = max(1, int(remain + 0.999))
            if remain_sec != last_shown:
                self._emit({
                    "type": "countdown",
                    "index": index,
                    "remaining": remain_sec,
                    "total": total,
                })
                last_shown = remain_sec
            time.sleep(min(0.25, remain))
        self._emit({"type": "countdown_done", "index": index})
        return True

    def _emit(self, event: dict) -> None:
        with self._sub_lock:
            subscribers = list(self._event_subscribers)
        for q in subscribers:
            try:
                q.put_nowait(event)
            except queue.Full:
                pass
        if not self._window:
            return
        payload = json.dumps(event, ensure_ascii=False)
        try:
            self._window.evaluate_js(f"window.onBatchEvent({payload})")
        except Exception:  # noqa: BLE001
            pass

    def _run_batch(self, params: dict) -> None:
        api_url = params.get("api_url", "")
        protocol = params.get("protocol", "http")
        target = params.get("target", "")
        regex = params.get("regex", "")
        interval_info = parse_batch_interval(
            params.get("interval", 0),
            params.get("interval_unit", "s"),
        )
        interval_seconds = interval_info.get("seconds", 0.0) if interval_info.get("ok") else 0.0
        unlimited = bool(interval_info.get("unlimited"))
        try:
            count = int(params.get("count", 10))
        except (TypeError, ValueError):
            count = 10
        if not unlimited:
            count = max(1, count)
        try:
            timeout = float(params.get("timeout", 10))
        except (TypeError, ValueError):
            timeout = 10.0
        dns_server = (params.get("dns_server") or "").strip() or _load_config().get("udp_dns", "8.8.8.8")
        username = (params.get("username") or "").strip()
        password = params.get("password") or ""
        show_content = bool(params.get("show_response_content", True))
        sync_browser = bool(params.get("sync_browser"))

        success = 0
        total_time = 0
        done = 0
        stopped = False
        self._emit({
            "type": "start",
            "count": count,
            "unlimited": unlimited,
            "interval_seconds": interval_seconds,
        })

        i = 0
        while True:
            if not unlimited and i >= count:
                break
            if self._stop.is_set():
                stopped = True
                self._emit({"type": "stopped", "index": i})
                break

            i += 1
            self._emit({"type": "fetching", "index": i})
            fetched = fetch_proxy_from_api(api_url, regex, timeout)

            if fetched.get("stage") == "fetch" and not fetched.get("ok"):
                self._emit({
                    "type": "result", "index": i, "ok": False,
                    "stage": "fetch", "error": fetched.get("error", ""),
                })
                done += 1
                self._emit_progress(done, count, success, total_time, unlimited)
                if unlimited:
                    if not self._wait_interval(interval_seconds, i):
                        stopped = True
                        self._emit({"type": "stopped", "index": i})
                        break
                time.sleep(0.2)
                continue

            if fetched.get("stage") == "parse":
                msg = fetched.get("error", "")
                self._emit({
                    "type": "result", "index": i, "ok": False,
                    "stage": "parse", "error": msg, "raw": fetched.get("raw", ""),
                })
                done += 1
                self._emit_progress(done, count, success, total_time, unlimited)
                self._emit({
                    "type": "aborted",
                    "index": i,
                    "error": msg,
                })
                break

            host, port = fetched["host"], fetched["port"]
            if fetched.get("multiple") and i == 1:
                self._emit({
                    "type": "hint",
                    "index": i,
                    "message": fetched.get("hint", ""),
                })

            self._emit({"type": "testing", "index": i, "host": host, "port": port})

            if self._stop.is_set():
                stopped = True
                self._emit({"type": "stopped", "index": i})
                break

            cycle = test_proxy_cycle(
                host, port, protocol, target, timeout,
                dns_server=dns_server,
                username=username,
                password=password,
                show_content=show_content,
                sync_browser=sync_browser,
            )

            done += 1
            if cycle.get("ok"):
                success += 1
                total_time += cycle.get("elapsed_ms", 0)
            self._emit({
                "type": "result", "index": i, "ok": cycle.get("ok", False),
                "stage": "test", "host": host, "port": port,
                "elapsed_ms": cycle.get("elapsed_ms", 0),
                "status": cycle.get("status"),
                "content": cycle.get("content", ""),
                "error": cycle.get("error", ""),
                "note": cycle.get("note", ""),
                "public_ip": cycle.get("public_ip", ""),
            })
            self._emit_progress(done, count, success, total_time, unlimited)

            if self._stop.is_set():
                stopped = True
                self._emit({"type": "stopped", "index": i})
                break

            if unlimited:
                self._emit({"type": "waiting", "index": i, "seconds": interval_seconds})
                if not self._wait_interval(interval_seconds, i):
                    stopped = True
                    self._emit({"type": "stopped", "index": i})
                    break

        if sync_browser and not is_android():
            _restore_before_extract()

        self._emit({
            "type": "finished",
            "done": done,
            "success": success,
            "rate": round(success / done * 100, 1) if done else 0,
            "avg_ms": round(total_time / success) if success else 0,
            "stopped": stopped,
            "unlimited": unlimited,
            "sync_browser": sync_browser,
        })

    def _emit_progress(self, done: int, count: int, success: int, total_time: int,
                       unlimited: bool = False) -> None:
        self._emit({
            "type": "progress",
            "done": done,
            "count": count,
            "success": success,
            "unlimited": unlimited,
            "rate": round(success / done * 100, 1) if done else 0,
            "avg_ms": round(total_time / success) if success else 0,
        })
