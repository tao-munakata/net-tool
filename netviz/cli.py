from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from netviz import db
from netviz.collectors import lan, quality, traceroute, wan, wifi
from netviz.geo import enrich_ip


def db_path(value: str | None = None) -> Path:
    return Path(value or os.environ.get("NETVIZ_DB") or db.DEFAULT_DB).expanduser()


def write_measurements(conn, payload: dict[str, Any]) -> None:
    if payload.get("wifi"):
        db.insert_wifi(conn, payload["wifi"])
    if payload.get("lan"):
        db.insert_lan(conn, payload["lan"])
    if payload.get("wan"):
        db.insert_wan(conn, payload["wan"])
    if payload.get("dns"):
        db.insert_dns(conn, payload["dns"])
    if payload.get("quality"):
        db.insert_quality(conn, payload["quality"])
    for trace in payload.get("traces", []):
        for hop in trace.get("hops", []):
            geo = enrich_ip(conn, hop.get("ip"))
            loc = (geo.get("loc") or "").split(",", 1)
            hop["asn"] = (geo.get("org") or "").split(" ", 1)[0] or None
            hop["org"] = geo.get("org")
            hop["country"] = geo.get("country")
            if len(loc) == 2:
                try:
                    hop["lat"], hop["lng"] = float(loc[0]), float(loc[1])
                except ValueError:
                    pass
        db.insert_trace(conn, trace)
    conn.commit()


def collect_once(include_slow: bool = False) -> dict[str, Any]:
    payload: dict[str, Any] = {"errors": []}
    collectors = [
        ("wifi", wifi.collect),
        ("lan", lan.collect),
        ("wan", wan.collect_wan),
        ("dns", wan.collect_dns),
    ]
    if include_slow:
        collectors.extend(
            [
                ("quality", lambda: quality.collect(fast=False)),
                ("traces", lambda: [traceroute.collect("1.1.1.1"), traceroute.collect("8.8.8.8")]),
            ]
        )
    else:
        collectors.append(("quality", lambda: quality.collect(fast=True)))

    for name, func in collectors:
        try:
            payload[name] = func()
        except Exception as exc:  # noqa: BLE001 - collectors must not stop the whole run
            payload["errors"].append({"collector": name, "message": str(exc)})
    return payload


def cmd_once(args: argparse.Namespace) -> int:
    payload = collect_once(include_slow=args.slow)
    with db.connect(db_path(args.db)) as conn:
        write_measurements(conn, payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_collect(args: argparse.Namespace) -> int:
    if args.serve:
        from netviz.server import run_server_in_thread

        run_server_in_thread(db_path(args.db), args.port)
        print(f"dashboard: http://localhost:{args.port}")

    with db.connect(db_path(args.db)) as conn:
        while True:
            payload = collect_once(include_slow=False)
            write_measurements(conn, payload)
            print(json.dumps({"ts": payload.get("wifi", {}).get("ts"), "errors": payload.get("errors", [])}, ensure_ascii=False))
            time.sleep(args.interval)


def cmd_serve(args: argparse.Namespace) -> int:
    from netviz.server import serve

    serve(db_path(args.db), args.port)
    return 0


def _since_to_ms(value: str) -> int:
    unit = value[-1]
    amount = int(value[:-1])
    seconds = amount * {"h": 3600, "d": 86400, "m": 60}.get(unit, 3600)
    return int(time.time() * 1000) - seconds * 1000


def cmd_export(args: argparse.Namespace) -> int:
    since = _since_to_ms(args.since)
    tables = ["wifi_metrics", "lan_metrics", "wan_metrics", "dns_metrics", "quality_metrics"]
    with db.connect(db_path(args.db)) as conn:
        for table in tables:
            rows = db.rows_since(conn, table, since)
            if not rows:
                continue
            writer = csv.DictWriter(sys.stdout, fieldnames=["table", *rows[0].keys()])
            writer.writeheader()
            for row in rows:
                writer.writerow({"table": table, **row})
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="netviz")
    parser.add_argument("--db", help="SQLite DB path (default: ./metrics.db or NETVIZ_DB)")
    sub = parser.add_subparsers(dest="command", required=True)

    once = sub.add_parser("once", help="run collectors once and print JSON")
    once.add_argument("--slow", action="store_true", help="include traceroute and networkquality")
    once.set_defaults(func=cmd_once)

    collect = sub.add_parser("collect", help="run collectors in a loop")
    collect.add_argument("--interval", type=int, default=30)
    collect.add_argument("--serve", action="store_true")
    collect.add_argument("--port", type=int, default=8765)
    collect.set_defaults(func=cmd_collect)

    serve_parser = sub.add_parser("serve", help="serve dashboard")
    serve_parser.add_argument("--port", type=int, default=8765)
    serve_parser.set_defaults(func=cmd_serve)

    export = sub.add_parser("export", help="export recent metrics as CSV")
    export.add_argument("--since", default="1d")
    export.set_defaults(func=cmd_export)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
