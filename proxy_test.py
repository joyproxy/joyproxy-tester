"""Core proxy testing logic for JoyProxy Test.

Supports three proxy modes:
  - "http"    : HTTP/HTTPS proxy over TCP (CONNECT)
  - "s5_tcp"  : SOCKS5 proxy over TCP
  - "s5_udp"  : SOCKS5 proxy with UDP ASSOCIATE (real UDP relay test via DNS)

Every test is fully self contained and synchronous so the caller can run them
strictly one after another (no concurrency).
"""

from __future__ import annotations

import os
import random
import socket
import struct
import time
from dataclasses import dataclass, asdict
from typing import Optional
from urllib.parse import quote, urlparse

import requests


@dataclass
class TestResult:
    ok: bool
    elapsed_ms: int
    status: Optional[int] = None
    content: str = ""
    error: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


_DEF_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "*/*",
}

_MAX_CONTENT = 4000


def _trim(text: str) -> str:
    text = (text or "").strip()
    if len(text) > _MAX_CONTENT:
        return text[:_MAX_CONTENT] + "\n... (truncated)"
    return text


def _norm_auth(username: Optional[str], password: Optional[str]) -> tuple[str, str]:
    return (username or "").strip(), password or ""


def _auth_len_error(username: Optional[str], password: Optional[str]) -> Optional[str]:
    user, pwd = _norm_auth(username, password)
    if not user:
        return None
    u_len = len(user.encode("utf-8"))
    p_len = len(pwd.encode("utf-8"))
    if u_len > 255 or p_len > 255:
        return (
            f"SOCKS5 username/password must be at most 255 bytes "
            f"(username {u_len} bytes, password {p_len} bytes)"
        )
    return None


def _build_proxy_url(scheme: str, host: str, port: int,
                     username: Optional[str] = None, password: Optional[str] = None) -> str:
    user, pwd = _norm_auth(username, password)
    if user:
        return f"{scheme}://{quote(user, safe='')}:{quote(pwd, safe='')}@{host}:{port}"
    return f"{scheme}://{host}:{port}"


def _socks5_handshake(tcp: socket.socket, username: Optional[str] = None,
                      password: Optional[str] = None) -> Optional[str]:
    """Perform SOCKS5 greeting and optional username/password auth."""
    user, pwd = _norm_auth(username, password)
    if user:
        tcp.sendall(b"\x05\x01\x02")
        resp = tcp.recv(2)
        if len(resp) < 2 or resp[0] != 0x05:
            return "SOCKS5 handshake failed"
        if resp[1] != 0x02:
            return "Proxy does not support username/password authentication"
        u = user.encode("utf-8")
        p = pwd.encode("utf-8")
        if len(u) > 255 or len(p) > 255:
            return "Username or password is too long"
        tcp.sendall(b"\x01" + bytes([len(u)]) + u + bytes([len(p)]) + p)
        auth = tcp.recv(2)
        if len(auth) < 2 or auth[1] != 0x00:
            return "Proxy credential verification failed"
        return None

    tcp.sendall(b"\x05\x01\x00")
    resp = tcp.recv(2)
    if len(resp) < 2 or resp[0] != 0x05 or resp[1] != 0x00:
        return "Proxy does not support unauthenticated SOCKS5"
    return None


def test_http_like(host: str, port: int, target: str, timeout: float, scheme: str,
                   username: Optional[str] = None, password: Optional[str] = None,
                   fetch_content: bool = True) -> TestResult:
    """Run an HTTP GET to `target` through an http or socks5 proxy.

    scheme is one of: 'http', 'socks5h'
    """
    if scheme == "socks5h":
        auth_err = _auth_len_error(username, password)
        if auth_err:
            return TestResult(ok=False, elapsed_ms=0, error=auth_err)
    proxy_url = _build_proxy_url(scheme, host, port, username, password)
    proxies = {"http": proxy_url, "https": proxy_url}
    start = time.perf_counter()
    try:
        resp = requests.get(
            target,
            proxies=proxies,
            timeout=timeout,
            headers=_DEF_HEADERS,
            verify=False,
            allow_redirects=True,
            stream=not fetch_content,
        )
        elapsed = int((time.perf_counter() - start) * 1000)
        body = ""
        if fetch_content:
            try:
                body = resp.text
            except Exception:
                body = "<binary content>"
        else:
            resp.close()
        return TestResult(
            ok=True,
            elapsed_ms=elapsed,
            status=resp.status_code,
            content=_trim(body),
        )
    except requests.exceptions.RequestException as exc:
        elapsed = int((time.perf_counter() - start) * 1000)
        return TestResult(ok=False, elapsed_ms=elapsed, error=_describe_exc(exc))
    except Exception as exc:  # noqa: BLE001
        elapsed = int((time.perf_counter() - start) * 1000)
        return TestResult(ok=False, elapsed_ms=elapsed, error=str(exc))


def _describe_exc(exc: Exception) -> str:
    name = type(exc).__name__
    msg = str(exc)
    if "timed out" in msg.lower() or "timeout" in name.lower():
        return "Connection timed out"
    if "Connection refused" in msg or "refused" in msg.lower():
        return "Connection refused"
    if "Max retries" in msg:
        return "Unable to connect to proxy (Max retries)"
    return f"{name}: {msg}"


# --------------------------------------------------------------------------- #
# SOCKS5 UDP ASSOCIATE test (real UDP relay verification using a DNS query)
# --------------------------------------------------------------------------- #

def _build_dns_query(hostname: str) -> bytes:
    """Build a minimal DNS A-record query for hostname."""
    tid = random.randint(0, 0xFFFF)
    header = struct.pack(">HHHHHH", tid, 0x0100, 1, 0, 0, 0)
    qname = b"".join(
        struct.pack("B", len(part)) + part.encode("ascii")
        for part in hostname.split(".") if part
    ) + b"\x00"
    question = qname + struct.pack(">HH", 1, 1)  # type A, class IN
    return header + question


def _parse_dns_answer(data: bytes) -> str:
    """Parse A records out of a DNS response. Returns comma separated IPs."""
    try:
        (_tid, _flags, qd, an, _ns, _ar) = struct.unpack(">HHHHHH", data[:12])
        idx = 12
        for _ in range(qd):
            while idx < len(data) and data[idx] != 0:
                idx += data[idx] + 1
            idx += 1 + 4  # null byte + qtype + qclass
        ips = []
        for _ in range(an):
            # name (may be a pointer)
            if data[idx] & 0xC0 == 0xC0:
                idx += 2
            else:
                while idx < len(data) and data[idx] != 0:
                    idx += data[idx] + 1
                idx += 1
            rtype, _rclass, _ttl, rdlen = struct.unpack(">HHIH", data[idx:idx + 10])
            idx += 10
            rdata = data[idx:idx + rdlen]
            idx += rdlen
            if rtype == 1 and rdlen == 4:
                ips.append(".".join(str(b) for b in rdata))
        return ", ".join(ips) if ips else "(no A record)"
    except Exception:  # noqa: BLE001
        return "(unparsable DNS response)"


def test_socks5_udp(host: str, port: int, target: str, timeout: float,
                    dns_server: str = "8.8.8.8",
                    username: Optional[str] = None, password: Optional[str] = None,
                    fetch_content: bool = True) -> TestResult:
    """Verify SOCKS5 UDP ASSOCIATE works by relaying a DNS query through it.

    Measures the full round trip time of a UDP datagram through the proxy.
    """
    hostname = urlparse(target).hostname or "ipinfo.io"
    auth_err = _auth_len_error(username, password)
    if auth_err:
        return TestResult(ok=False, elapsed_ms=0, error=auth_err)
    start = time.perf_counter()
    tcp = None
    udp = None
    try:
        tcp = socket.create_connection((host, port), timeout=timeout)
        tcp.settimeout(timeout)
        auth_err = _socks5_handshake(tcp, username, password)
        if auth_err:
            return _udp_fail(start, auth_err)

        # UDP ASSOCIATE request, DST 0.0.0.0:0
        req = b"\x05\x03\x00\x01" + b"\x00\x00\x00\x00" + b"\x00\x00"
        tcp.sendall(req)
        reply = tcp.recv(10)
        if len(reply) < 2 or reply[1] != 0x00:
            return _udp_fail(start, "Proxy rejected UDP ASSOCIATE")

        atyp = reply[3]
        if atyp == 0x01:
            bnd_ip = socket.inet_ntoa(reply[4:8])
            bnd_port = struct.unpack(">H", reply[8:10])[0]
        elif atyp == 0x04:
            extra = tcp.recv(12 - len(reply) + 4)
            full = reply + extra
            bnd_ip = socket.inet_ntop(socket.AF_INET6, full[4:20])
            bnd_port = struct.unpack(">H", full[20:22])[0]
        else:
            return _udp_fail(start, "Proxy returned an unparseable address type")

        # If the proxy returns 0.0.0.0 use the proxy host itself for the relay
        if bnd_ip in ("0.0.0.0", "::"):
            bnd_ip = host

        # Build SOCKS5 UDP datagram: RSV(2) FRAG(1) ATYP DST.ADDR DST.PORT DATA
        dns_payload = _build_dns_query(hostname)
        dst = (
            b"\x00\x00\x00\x01"
            + socket.inet_aton(dns_server)
            + struct.pack(">H", 53)
        )
        datagram = dst + dns_payload

        udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp.settimeout(timeout)
        udp.sendto(datagram, (bnd_ip, bnd_port))
        data, _ = udp.recvfrom(4096)
        elapsed = int((time.perf_counter() - start) * 1000)

        # strip the 10-byte SOCKS5 UDP header from the reply (IPv4 case)
        if len(data) > 10:
            inner = data[10:]
            ips = _parse_dns_answer(inner)
        else:
            ips = "(empty response)"
        content = ""
        if fetch_content:
            content = (
                f"SOCKS5 UDP ASSOCIATE succeeded\n"
                f"Relay address: {bnd_ip}:{bnd_port}\n"
                f"UDP DNS via proxy: {hostname} -> {ips}\n"
                f"(Verified UDP relay via DNS query to {dns_server}:53)"
            )
        return TestResult(ok=True, elapsed_ms=elapsed, status=200, content=content)
    except socket.timeout:
        return _udp_fail(start, "Connection timed out")
    except ConnectionRefusedError:
        return _udp_fail(start, "Connection refused")
    except Exception as exc:  # noqa: BLE001
        return _udp_fail(start, f"{type(exc).__name__}: {exc}")
    finally:
        for s in (udp, tcp):
            try:
                if s:
                    s.close()
            except Exception:  # noqa: BLE001
                pass


def _udp_fail(start: float, msg: str) -> TestResult:
    elapsed = int((time.perf_counter() - start) * 1000)
    return TestResult(ok=False, elapsed_ms=elapsed, error=msg)


# --------------------------------------------------------------------------- #
# Dispatcher
# --------------------------------------------------------------------------- #

def run_test(host: str, port: int, protocol: str, target: str, timeout: float,
             dns_server: str = "8.8.8.8",
             username: Optional[str] = None, password: Optional[str] = None,
             fetch_content: bool = True) -> TestResult:
    host = (host or "").strip()
    try:
        port = int(port)
    except (TypeError, ValueError):
        return TestResult(ok=False, elapsed_ms=0, error="Invalid port")
    if not host:
        return TestResult(ok=False, elapsed_ms=0, error="Proxy address is empty")
    if not (0 < port < 65536):
        return TestResult(ok=False, elapsed_ms=0, error="Port out of range")

    protocol = (protocol or "http").lower()
    if protocol == "http":
        return test_http_like(host, port, target, timeout, "http", username, password,
                              fetch_content=fetch_content)
    if protocol == "s5_tcp":
        return test_http_like(host, port, target, timeout, "socks5h", username, password,
                              fetch_content=fetch_content)
    if protocol == "s5_udp":
        dns = (dns_server or "8.8.8.8").strip() or "8.8.8.8"
        return test_socks5_udp(host, port, target, timeout, dns_server=dns,
                               username=username, password=password,
                               fetch_content=fetch_content)
    return TestResult(ok=False, elapsed_ms=0, error=f"Unknown protocol: {protocol}")
