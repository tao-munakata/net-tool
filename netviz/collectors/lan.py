from __future__ import annotations

import re
from typing import Any

from netviz.util import is_linux, now_ms, parse_ping, ping_args, run_command


def gateway_ip() -> str | None:
    if is_linux():
        code, out, _ = run_command(["ip", "route", "show", "default"], timeout=3)
        if code != 0:
            return None
        match = re.search(r"\bvia\s+([0-9.]+)", out)
        return match.group(1) if match else None

    code, out, _ = run_command(["route", "-n", "get", "default"], timeout=3)
    if code != 0:
        return None
    match = re.search(r"gateway:\s*([0-9.]+)", out)
    return match.group(1) if match else None


def parse_arp(output: str, linux: bool = False) -> list[dict[str, str | None]]:
    entries: list[dict[str, str | None]] = []
    for line in output.splitlines():
        if linux:
            match = re.search(r"^([0-9.]+)\s+dev\s+(\S+)(?:\s+lladdr\s+([0-9a-f:]+))?", line, re.I)
            if match:
                entries.append({"ip": match.group(1), "mac": match.group(3), "iface": match.group(2)})
            continue
        match = re.search(r"\(([^)]+)\)\s+at\s+([0-9a-f:]+|incomplete)\s+on\s+(\S+)", line, re.I)
        if match:
            entries.append({"ip": match.group(1), "mac": match.group(2), "iface": match.group(3)})
    return entries


def collect() -> dict[str, Any]:
    ts = now_ms()
    gw = gateway_ip()
    ping = {"avg_ms": None, "jitter_ms": None, "loss_pct": None}
    if gw:
        code, out, _ = run_command(ping_args(gw, count=5, deadline=2), timeout=8)
        if code in (0, 2):
            ping = parse_ping(out)

    if is_linux():
        code, out, _ = run_command(["ip", "neigh", "show"], timeout=3)
        arp_entries = parse_arp(out, linux=True) if code == 0 else []
    else:
        code, out, _ = run_command(["arp", "-an"], timeout=3)
        arp_entries = parse_arp(out) if code == 0 else []
    return {
        "ts": ts,
        "gateway_ip": gw,
        "gw_rtt_avg_ms": ping["avg_ms"],
        "gw_rtt_jitter_ms": ping["jitter_ms"],
        "gw_loss_pct": ping["loss_pct"],
        "arp_entries": arp_entries,
    }
