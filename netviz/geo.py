from __future__ import annotations

import ipaddress
import json
import sqlite3
from typing import Any

from netviz.util import load_json, now_ms, run_command

CACHE_MS = 24 * 60 * 60 * 1000


def enrich_ip(conn: sqlite3.Connection, ip: str | None) -> dict[str, Any]:
    if not ip:
        return {}
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return {}
    if addr.is_private or addr.is_loopback or addr.is_link_local:
        return {}

    ts = now_ms()
    row = conn.execute("SELECT payload, fetched_at FROM geo_cache WHERE ip = ?", (ip,)).fetchone()
    if row and ts - int(row["fetched_at"]) < CACHE_MS:
        return json.loads(row["payload"])

    code, out, _ = run_command(["curl", "-s", f"https://ipinfo.io/{ip}/json"], timeout=5)
    data = load_json(out) if code == 0 else {}
    if data:
        conn.execute(
            "INSERT OR REPLACE INTO geo_cache (ip, payload, fetched_at) VALUES (?, ?, ?)",
            (ip, json.dumps(data), ts),
        )
    return data
