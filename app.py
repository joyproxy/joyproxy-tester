"""JoyProxy Tester - portable proxy IP testing tool.

Entry point: creates a pywebview window backed by Edge WebView2 (built into
Windows 10/11) and loads the local web UI.
"""

from __future__ import annotations

import os

import webview

from backend import Api
from platform_utils import web_dir


def _web_path(name: str) -> str:
    return os.path.join(web_dir(), name)


def main() -> None:
    # silence noisy InsecureRequestWarning from verify=False proxy tests
    try:
        import urllib3
        urllib3.disable_warnings()
    except Exception:  # noqa: BLE001
        pass

    api = Api()
    window = webview.create_window(
        title="JoyProxy Tester",
        url=_web_path("index.html"),
        js_api=api,
        width=1180,
        height=720,
        min_size=(960, 640),
        background_color="#0B0F1A",
    )
    api.set_window(window)
    webview.start(debug=False)


if __name__ == "__main__":
    main()
