from __future__ import annotations

import json
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from typing import Any

from netviz import db
from netviz.util import iso_from_ms

APP_DIR = Path(__file__).resolve().parent.parent
WEB_DIR = APP_DIR / "web"


def parse_since(value: str) -> int:
    unit = value[-1]
    amount = int(value[:-1])
    seconds = amount * {"m": 60, "h": 3600, "d": 86400}.get(unit, 3600)
    return int(time.time() * 1000) - seconds * 1000


def decorate_ts(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    out = dict(row)
    if "ts" in out and out["ts"]:
        out["ts_iso"] = iso_from_ms(int(out["ts"]))
    if "arp_entries" in out and isinstance(out["arp_entries"], str):
        try:
            out["arp_entries"] = json.loads(out["arp_entries"])
        except json.JSONDecodeError:
            out["arp_entries"] = []
    return out


def snapshot_payload(db_file: Path) -> dict[str, Any]:
    since_1h = parse_since("1h")
    with db.connect(db_file) as conn:
        ping_errors = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM quality_metrics
            WHERE ts >= ?
              AND source = 'ping'
              AND (ping_loss_pct >= 100 OR ping_avg_ms IS NULL)
            """,
            (since_1h,),
        ).fetchone()["count"]
        dns_errors = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM dns_metrics
            WHERE ts >= ?
              AND query_ms IS NULL
            """,
            (since_1h,),
        ).fetchone()["count"]
        return {
            "wifi": decorate_ts(db.latest(conn, "wifi_metrics")),
            "lan": decorate_ts(db.latest(conn, "lan_metrics")),
            "wan": decorate_ts(db.latest(conn, "wan_metrics")),
            "quality": decorate_ts(db.latest(conn, "quality_metrics")),
            "dns": [decorate_ts(dict(row)) for row in conn.execute("SELECT * FROM dns_metrics ORDER BY ts DESC LIMIT 6")],
            "errors": {
                "since": "1h",
                "ping": ping_errors,
                "dns": dns_errors,
            },
        }


def latest_traces_payload(db_file: Path) -> list[dict[str, Any]]:
    with db.connect(db_file) as conn:
        traces = conn.execute("SELECT * FROM traces ORDER BY ts DESC LIMIT 3").fetchall()
        out = []
        for trace in traces:
            hops = conn.execute("SELECT * FROM hops WHERE trace_id = ? ORDER BY hop_no", (trace["id"],)).fetchall()
            item = decorate_ts(dict(trace)) or {}
            item["hops"] = [dict(hop) for hop in hops]
            out.append(item)
        return out


def create_app(db_file: Path):
    from fastapi import FastAPI
    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles

    app = FastAPI(title="Network Visualizer")
    app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(WEB_DIR / "index.html")

    @app.get("/api/snapshot")
    def snapshot() -> dict[str, Any]:
        return snapshot_payload(db_file)

    @app.get("/api/wifi")
    def wifi_series(since: str = "1h") -> list[dict[str, Any]]:
        with db.connect(db_file) as conn:
            return [decorate_ts(row) for row in db.rows_since(conn, "wifi_metrics", parse_since(since))]

    @app.get("/api/quality")
    def quality_series(since: str = "24h") -> list[dict[str, Any]]:
        with db.connect(db_file) as conn:
            return [decorate_ts(row) for row in db.rows_since(conn, "quality_metrics", parse_since(since))]

    @app.get("/api/traces/latest")
    def latest_traces() -> list[dict[str, Any]]:
        return latest_traces_payload(db_file)

    @app.get("/api/traces/{trace_id}")
    def trace_by_id(trace_id: int) -> dict[str, Any]:
        with db.connect(db_file) as conn:
            trace = conn.execute("SELECT * FROM traces WHERE id = ?", (trace_id,)).fetchone()
            if not trace:
                return {}
            hops = conn.execute("SELECT * FROM hops WHERE trace_id = ? ORDER BY hop_no", (trace_id,)).fetchall()
            item = decorate_ts(dict(trace)) or {}
            item["hops"] = [dict(hop) for hop in hops]
            return item

    @app.get("/api/lan/devices")
    def lan_devices() -> list[dict[str, Any]]:
        with db.connect(db_file) as conn:
            row = decorate_ts(db.latest(conn, "lan_metrics"))
            return row.get("arp_entries", []) if row else []

    return app


class NetvizHandler(SimpleHTTPRequestHandler):
    db_file: Path

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=WEB_DIR, **kwargs)

    def _send_json(self, payload: Any) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        if parsed.path == "/":
            self.path = "/index.html"
            return super().do_GET()
        if parsed.path.startswith("/static/"):
            self.path = parsed.path.removeprefix("/static")
            return super().do_GET()
        if parsed.path == "/api/snapshot":
            return self._send_json(snapshot_payload(self.db_file))
        if parsed.path == "/api/wifi":
            since = query.get("since", ["1h"])[0]
            with db.connect(self.db_file) as conn:
                return self._send_json([decorate_ts(row) for row in db.rows_since(conn, "wifi_metrics", parse_since(since))])
        if parsed.path == "/api/quality":
            since = query.get("since", ["24h"])[0]
            with db.connect(self.db_file) as conn:
                return self._send_json([decorate_ts(row) for row in db.rows_since(conn, "quality_metrics", parse_since(since))])
        if parsed.path == "/api/traces/latest":
            return self._send_json(latest_traces_payload(self.db_file))
        if parsed.path.startswith("/api/traces/"):
            trace_id = int(parsed.path.rsplit("/", 1)[-1])
            with db.connect(self.db_file) as conn:
                trace = conn.execute("SELECT * FROM traces WHERE id = ?", (trace_id,)).fetchone()
                if not trace:
                    return self._send_json({})
                hops = conn.execute("SELECT * FROM hops WHERE trace_id = ? ORDER BY hop_no", (trace_id,)).fetchall()
                item = decorate_ts(dict(trace)) or {}
                item["hops"] = [dict(hop) for hop in hops]
                return self._send_json(item)
        if parsed.path == "/api/lan/devices":
            with db.connect(self.db_file) as conn:
                row = decorate_ts(db.latest(conn, "lan_metrics"))
                return self._send_json(row.get("arp_entries", []) if row else [])
        return super().do_GET()


def serve_stdlib(db_file: Path, port: int) -> None:
    NetvizHandler.db_file = db_file
    server = ThreadingHTTPServer(("127.0.0.1", port), NetvizHandler)
    print(f"dashboard: http://localhost:{port}")
    server.serve_forever()


def serve(db_file: Path, port: int = 8765) -> None:
    try:
        import uvicorn

        uvicorn.run(create_app(db_file), host="127.0.0.1", port=port, log_level="info")
    except ModuleNotFoundError:
        serve_stdlib(db_file, port)


def run_server_in_thread(db_file: Path, port: int = 8765) -> threading.Thread:
    thread = threading.Thread(target=serve, args=(db_file, port), daemon=True)
    thread.start()
    return thread
