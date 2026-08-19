"""Flask HTTP server for Android WebView and local debugging."""

from __future__ import annotations

import json
import os
import queue
import threading
import time
from typing import Optional

from flask import Flask, Response, jsonify, request, send_from_directory

from backend import Api
from platform_utils import is_android, web_dir
from version import __version__

HOST = "127.0.0.1"
PORT = 17890

_api: Optional[Api] = None
_api_lock = threading.Lock()


def get_api() -> Api:
    global _api
    with _api_lock:
        if _api is None:
            _api = Api()
        return _api


def create_app() -> Flask:
    try:
        import urllib3

        urllib3.disable_warnings()
    except Exception:  # noqa: BLE001
        pass

    app = Flask(__name__)
    root = web_dir()

    @app.get("/api/ping")
    def ping():
        return jsonify({
            "ok": True,
            "platform": "android" if is_android() else "desktop",
            "version": __version__,
        })

    @app.post("/api/rpc")
    def rpc():
        body = request.get_json(force=True, silent=True) or {}
        method = body.get("method", "")
        kwargs = body.get("kwargs") or {}
        api = get_api()
        target = getattr(api, method, None)
        if not callable(target):
            return jsonify({"ok": False, "error": f"Unknown method: {method}"}), 400
        try:
            result = target(**kwargs)
            return jsonify(result)
        except TypeError as exc:
            return jsonify({"ok": False, "error": f"Invalid parameters: {exc}"}), 400
        except Exception as exc:  # noqa: BLE001
            return jsonify({"ok": False, "error": str(exc)}), 500

    @app.get("/api/batch/events")
    def batch_events():
        api = get_api()
        q = api.subscribe_events()

        def stream():
            try:
                yield ": connected\n\n"
                while True:
                    try:
                        event = q.get(timeout=15)
                    except queue.Empty:
                        yield ": keepalive\n\n"
                        continue
                    payload = json.dumps(event, ensure_ascii=False)
                    yield f"data: {payload}\n\n"
            finally:
                api.unsubscribe_events(q)

        return Response(stream(), mimetype="text/event-stream")

    @app.get("/")
    def index():
        path = os.path.join(root, "index.html")
        with open(path, "r", encoding="utf-8") as fh:
            html = fh.read()
        if is_android():
            html = html.replace("<body>", '<body class="platform-android">', 1)
        return Response(html, mimetype="text/html; charset=utf-8")

    @app.get("/<path:filename>")
    def static_files(filename: str):
        return send_from_directory(root, filename)

    return app


def run_server(host: str = HOST, port: int = PORT) -> None:
    app = create_app()
    app.run(host=host, port=port, threaded=True, use_reloader=False)


def run_dev() -> None:
    """Run Flask UI on desktop for testing the HTTP client."""
    threading.Thread(target=run_server, daemon=True).start()
    print(f"JoyProxy Tester HTTP mode: http://{HOST}:{PORT}/")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    run_dev()
