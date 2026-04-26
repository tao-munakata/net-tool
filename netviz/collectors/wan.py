from __future__ import annotations

import re
from typing import Any

from netviz.util import has_command, load_json, now_ms, run_command


def _loc(value: str | None) -> tuple[float | None, float | None]:
    if not value or "," not in value:
        return None, None
    lat, lng = value.split(",", 1)
    try:
        return float(lat), float(lng)
    except ValueError:
        return None, None


def public_ipinfo() -> dict[str, Any]:
    code, out, _ = run_command(["curl", "-s", "https://ipinfo.io/json"], timeout=6)
    if code != 0:
        return {}
    return load_json(out)


def collect_wan() -> dict[str, Any]:
    ts = now_ms()
    data = public_ipinfo()
    lat, lng = _loc(data.get("loc"))
    return {
        "ts": ts,
        "public_ip": data.get("ip"),
        "asn": data.get("org", "").split(" ", 1)[0] if data.get("org") else None,
        "org": data.get("org"),
        "country": data.get("country"),
        "region": data.get("region"),
        "city": data.get("city"),
        "loc_lat": lat,
        "loc_lng": lng,
    }


DIG_TIME_RE = re.compile(r"Query time:\s*(\d+)\s*msec")


def collect_dns(hostname: str = "google.com") -> list[dict[str, Any]]:
    ts = now_ms()
    resolvers = [("system", None), ("1.1.1.1", "1.1.1.1"), ("8.8.8.8", "8.8.8.8")]
    rows = []
    for label, resolver in resolvers:
        query_ms = None
        if has_command("dig"):
            args = ["dig"]
            if resolver:
                args.append(f"@{resolver}")
            args.extend([hostname, "+stats"])
            code, out, _ = run_command(args, timeout=5)
            match = DIG_TIME_RE.search(out) if code == 0 else None
            query_ms = float(match.group(1)) if match else None
        elif resolver is None and has_command("resolvectl"):
            start = now_ms()
            code, _, _ = run_command(["resolvectl", "query", hostname], timeout=5)
            query_ms = float(now_ms() - start) if code == 0 else None
        elif resolver is None:
            start = now_ms()
            code, _, _ = run_command(["getent", "hosts", hostname], timeout=5)
            query_ms = float(now_ms() - start) if code == 0 else None
        rows.append(
            {
                "ts": ts,
                "resolver": label,
                "hostname": hostname,
                "query_ms": query_ms,
            }
        )
    return rows
