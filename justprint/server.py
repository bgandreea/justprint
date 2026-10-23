"""Local HTTP server for the JustPrint window."""

from __future__ import annotations

import json
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from justprint.app import App
from justprint.paths import ui_dir

STATIC = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/app.css": ("app.css", "text/css; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/logo.png": ("logo.png", "image/png"),
}


def serve(app: App) -> ThreadingHTTPServer:
    handler = make_handler(app)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=httpd.serve_forever, name="justprint-http", daemon=True)
    thread.start()
    return httpd


def make_handler(app: App):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self):
            try:
                handle_get(app, self)
            except Exception as exc:
                send_json(self, 500, {"error": str(exc)})

        def do_POST(self):
            try:
                handle_post(app, self)
            except (RuntimeError, ValueError, KeyError, OSError) as exc:
                send_json(self, 400, {"error": str(exc)})
            except Exception as exc:
                send_json(self, 500, {"error": str(exc)})

        def log_message(self, fmt, *args):
            return

    return Handler


def handle_get(app: App, handler: BaseHTTPRequestHandler) -> None:
    route, query = _route(handler)
    if route == "/favicon.ico":
        handler.send_response(204)
        handler.send_header("Content-Length", "0")
        handler.end_headers()
        return
    if route == "/api/state":
        send_json(handler, 200, app.get_state())
        return
    if route.startswith("/api/preview/"):
        doc_id = route[len("/api/preview/") :]
        try:
            page = int((query.get("page") or ["1"])[0])
        except ValueError:
            send_json(handler, 400, {"error": "Page must be a number"})
            return
        png = app.preview_png(doc_id, page)
        if png is None:
            send_json(handler, 404, {"error": "No preview for that page"})
            return
        send_bytes(handler, 200, png, "image/png")
        return
    static = STATIC.get(route)
    if static is None:
        send_json(handler, 404, {"error": "Not found"})
        return
    name, content_type = static
    path = ui_dir() / name
    send_bytes(handler, 200, path.read_bytes(), content_type)


def handle_post(app: App, handler: BaseHTTPRequestHandler) -> None:
    route, _query = _route(handler)
    if route == "/api/drop":
        send_json(handler, 200, {"path": receive_drop(app, handler)})
        return
    payload = read_json(handler)
    if route == "/api/pick/files":
        send_json(handler, 200, app.pick_files())
    elif route == "/api/pick/folder":
        send_json(handler, 200, app.pick_folder())
    elif route == "/api/add":
        paths = payload.get("paths") or []
        if not isinstance(paths, list):
            raise ValueError("Paths must be a list")
        send_json(handler, 200, app.add_paths([str(path) for path in paths]))
    elif route == "/api/documents/update":
        app.update_document(payload)
        send_json(handler, 200, {"ok": True})
    elif route == "/api/documents/remove":
        ids = payload.get("ids") or []
        if not isinstance(ids, list):
            raise ValueError("Ids must be a list")
        app.remove_documents([str(doc_id) for doc_id in ids])
        send_json(handler, 200, {"ok": True})
    elif route == "/api/documents/remove-printed":
        app.remove_printed()
        send_json(handler, 200, {"ok": True})
    elif route == "/api/documents/clear":
        app.clear()
        send_json(handler, 200, {"ok": True})
    elif route == "/api/documents/select-all":
        app.select_all(bool(payload.get("selected")))
        send_json(handler, 200, {"ok": True})
    elif route == "/api/settings":
        app.update_settings(payload)
        send_json(handler, 200, {"ok": True})
    elif route == "/api/settings/reset":
        app.reset_settings()
        send_json(handler, 200, {"ok": True})
    elif route == "/api/settings/export":
        send_json(handler, 200, app.export_settings())
    elif route == "/api/settings/import":
        send_json(handler, 200, app.import_settings())
    elif route == "/api/settings/printer-defaults":
        send_json(handler, 200, app.adopt_printer_defaults())
    elif route == "/api/settings/printed-folder":
        send_json(handler, 200, app.pick_printed_folder())
    elif route == "/api/window/size":
        app.save_window_size(int(payload.get("width") or 0), int(payload.get("height") or 0))
        send_json(handler, 200, {"ok": True})
    elif route == "/api/summary/dismiss":
        app.dismiss_summary()
        send_json(handler, 200, {"ok": True})
    elif route == "/api/warning/dismiss":
        app.dismiss_warning()
        send_json(handler, 200, {"ok": True})
    elif route == "/api/print/start":
        app.start_print()
        send_json(handler, 200, {"ok": True})
    elif route == "/api/print/stop":
        app.stop()
        send_json(handler, 200, {"ok": True})
    elif route == "/api/print/test":
        app.start_test_page()
        send_json(handler, 200, {"ok": True})
    else:
        send_json(handler, 404, {"error": "Not found"})


def receive_drop(app: App, handler: BaseHTTPRequestHandler) -> str:
    length = int(handler.headers.get("Content-Length") or 0)
    if length < 0 or length > 200_000_000:
        handler.close_connection = True
        raise ValueError("That file is too large to drop here. Use Add files for files over 200 MB.")
    batch = urllib.parse.unquote(handler.headers.get("X-Drop-Batch") or "")
    name = urllib.parse.unquote(handler.headers.get("X-Drop-Name") or "")
    data = handler.rfile.read(length) if length else b""
    if length and len(data) != length:
        raise ValueError("The dropped file was incomplete")
    return app.store_drop(batch, name, data)


def read_json(handler: BaseHTTPRequestHandler) -> dict:
    length = int(handler.headers.get("Content-Length") or 0)
    if length > 2_000_000:
        raise ValueError("That request is too large")
    raw = handler.rfile.read(length) if length else b""
    if not raw:
        return {}
    try:
        data = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("That request was not valid") from exc
    if not isinstance(data, dict):
        raise ValueError("That request was not valid")
    return data


def send_json(handler: BaseHTTPRequestHandler, status: int, payload: dict) -> None:
    send_bytes(handler, status, json.dumps(payload).encode("utf-8"), "application/json; charset=utf-8")


def send_bytes(handler: BaseHTTPRequestHandler, status: int, body: bytes, content_type: str) -> None:
    try:
        handler.send_response(status)
        handler.send_header("Content-Type", content_type)
        handler.send_header("Content-Length", str(len(body)))
        handler.send_header("Cache-Control", "no-store")
        handler.end_headers()
        handler.wfile.write(body)
    except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
        return


def _route(handler: BaseHTTPRequestHandler) -> tuple[str, dict]:
    parsed = urllib.parse.urlparse(handler.path)
    route = urllib.parse.unquote(parsed.path)
    if route != "/" and route.endswith("/"):
        route = route.rstrip("/")
    return route, urllib.parse.parse_qs(parsed.query)
