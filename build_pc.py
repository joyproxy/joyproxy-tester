"""Build the Windows portable exe with the release filename."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from version import __version__

ROOT = Path(__file__).resolve().parent
PY = ROOT / ".venv" / "Scripts" / "python.exe"
if not PY.exists():
    PY = Path(sys.executable)

NAME = f"JoyProxy-Tester-{__version__}"
DIST = ROOT / "dist" / f"{NAME}.exe"


def run(cmd: list[str]) -> None:
    print("+", " ".join(cmd))
    subprocess.check_call(cmd, cwd=ROOT)


def main() -> None:
    run([str(PY), "-m", "pip", "install", "pyinstaller", "pillow"])
    run([
        str(PY), "-m", "PyInstaller",
        "--noconfirm", "--clean",
        "--windowed", "--onefile", "--noupx",
        "--name", NAME,
        "--icon", "logo.ico",
        "--add-data", "web;web",
        "app.py",
    ])
    if not DIST.exists():
        raise SystemExit(f"Build failed: missing {DIST}")
    print(f"\nBuild finished: {DIST}")
    print(f"Size: {DIST.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
