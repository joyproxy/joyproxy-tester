"""Parse proxy endpoint strings (host:port, user:pass@host:port, full URI)."""

from __future__ import annotations

import re
from typing import Any, Optional
from urllib.parse import unquote

_SCHEME_RE = re.compile(r"^(https?|socks5h?|socks4)://", re.I)


def _decode_part(text: str) -> str:
    try:
        return unquote(text or "")
    except Exception:  # noqa: BLE001
        return text or ""


def _parse_host_port(raw: str) -> Optional[tuple[str, int]]:
    text = (raw or "").strip()
    if not text:
        return None

    v6 = re.match(r"^\[([^\]]+)\]:(\d{1,5})$", text)
    if v6:
        port = int(v6.group(2))
        if 0 < port < 65536:
            return v6.group(1), port

    idx = text.rfind(":")
    if idx > 0:
        host = text[:idx]
        port_str = text[idx + 1 :]
        if re.fullmatch(r"\d{1,5}", port_str):
            port = int(port_str)
            if 0 < port < 65536:
                return host, port
    return None


def normalize_proxy_text(text: str) -> str:
    """Trim and normalize common paste quirks (e.g. fullwidth colon)."""
    return (text or "").strip().replace("\uFF1A", ":")


def parse_proxy_input(text: str) -> Optional[dict[str, Any]]:
    """Return host, port, username, password, and optional protocol from one line."""
    raw = normalize_proxy_text(text)
    if not raw:
        return None

    out: dict[str, Any] = {
        "host": "",
        "port": 0,
        "username": "",
        "password": "",
        "protocol": None,
    }

    scheme_match = _SCHEME_RE.match(raw)
    if scheme_match:
        scheme = scheme_match.group(1).lower()
        if scheme in ("http", "https"):
            out["protocol"] = "http"
        elif scheme in ("socks5", "socks5h", "socks4"):
            out["protocol"] = "s5_tcp"
        raw = raw[scheme_match.end() :]
        at_idx = raw.rfind("@")
        if at_idx >= 0:
            userinfo = raw[:at_idx]
            raw = raw[at_idx + 1 :]
            colon_idx = userinfo.find(":")
            if colon_idx >= 0:
                out["username"] = _decode_part(userinfo[:colon_idx])
                out["password"] = _decode_part(userinfo[colon_idx + 1 :])
            else:
                out["username"] = _decode_part(userinfo)
    else:
        raw = re.sub(r"^https?://", "", raw, flags=re.I).split("/")[0].split("?")[0]
        at_idx = raw.rfind("@")
        if at_idx >= 0:
            userinfo = raw[:at_idx]
            raw = raw[at_idx + 1 :]
            colon_idx = userinfo.find(":")
            if colon_idx >= 0:
                out["username"] = _decode_part(userinfo[:colon_idx])
                out["password"] = _decode_part(userinfo[colon_idx + 1 :])
            else:
                out["username"] = _decode_part(userinfo)

    host_port = _parse_host_port(raw.split("/")[0].split("?")[0])
    if not host_port:
        return None
    out["host"], out["port"] = host_port[0], host_port[1]
    return out


def resolve_proxy_fields(
    host: str,
    port,
    username: str = "",
    password: str = "",
    protocol: str = "",
) -> tuple[str, int, str, str, str, bool]:
    """Merge split UI fields with a pasted full proxy line in `host` (and optional `port`)."""
    host_s = normalize_proxy_text(host)
    port_s = str(port or "").strip()
    user = (username or "").strip()
    pwd = password or ""
    proto = (protocol or "").strip()

    candidates: list[str] = []
    if host_s:
        candidates.append(host_s)
    if host_s and port_s and not re.search(r":\d{1,5}$", host_s):
        candidates.append(f"{host_s}:{port_s}")

    parsed: Optional[dict[str, Any]] = None
    for candidate in candidates:
        parsed = parse_proxy_input(candidate)
        if parsed:
            break

    if not parsed:
        try:
            port_i = int(port_s)
        except (TypeError, ValueError):
            port_i = 0
        return host_s, port_i, user, pwd, proto, False

    if not user:
        user = (parsed.get("username") or "").strip()
    if not pwd:
        pwd = parsed.get("password") or ""

    parsed_proto = parsed.get("protocol")
    if not proto and parsed_proto:
        proto = str(parsed_proto)

    return (
        str(parsed["host"]),
        int(parsed["port"]),
        user,
        pwd,
        proto or "http",
        True,
    )
