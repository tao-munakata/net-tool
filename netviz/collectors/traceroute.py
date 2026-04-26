from __future__ import annotations

import re
from typing import Any

from netviz.util import has_command, now_ms, run_command

HOP_RE = re.compile(r"^\s*(\d+)\s+(.*)$")
IP_RE = re.compile(r"(\d{1,3}(?:\.\d{1,3}){3})")
RTT_RE = re.compile(r"([0-9.]+)\s*ms")


def parse_traceroute(output: str) -> list[dict[str, Any]]:
    hops: list[dict[str, Any]] = []
    for line in output.splitlines():
        match = HOP_RE.match(line)
        if not match:
            continue
        hop_no = int(match.group(1))
        rest = match.group(2)
        ip_match = IP_RE.search(rest)
        rtt_match = RTT_RE.search(rest)
        hops.append(
            {
                "hop_no": hop_no,
                "ip": ip_match.group(1) if ip_match else None,
                "rtt_ms": float(rtt_match.group(1)) if rtt_match else None,
                "asn": None,
                "org": None,
                "country": None,
                "lat": None,
                "lng": None,
            }
        )
    return hops


def parse_tracepath(output: str) -> list[dict[str, Any]]:
    hops: list[dict[str, Any]] = []
    for line in output.splitlines():
        match = re.match(r"^\s*(\d+):\s+(.*)$", line)
        if not match:
            continue
        rest = match.group(2)
        ip_match = IP_RE.search(rest)
        rtt_match = re.search(r"([0-9.]+)\s*ms", rest)
        hops.append(
            {
                "hop_no": int(match.group(1)),
                "ip": ip_match.group(1) if ip_match else None,
                "rtt_ms": float(rtt_match.group(1)) if rtt_match else None,
                "asn": None,
                "org": None,
                "country": None,
                "lat": None,
                "lng": None,
            }
        )
    return hops


def collect(target: str = "1.1.1.1") -> dict[str, Any]:
    ts = now_ms()
    if has_command("traceroute"):
        code, out, err = run_command(["traceroute", "-n", "-w", "2", "-q", "1", "-m", "20", target], timeout=50)
        hops = parse_traceroute(out if code in (0, 1) else err)
    elif has_command("tracepath"):
        code, out, err = run_command(["tracepath", "-n", "-m", "20", target], timeout=50)
        hops = parse_tracepath(out if code in (0, 1) else err)
    else:
        hops = []
    return {
        "ts": ts,
        "target": target,
        "hops": hops,
    }
