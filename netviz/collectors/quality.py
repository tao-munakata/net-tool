from __future__ import annotations

from typing import Any

from netviz.util import has_command, is_macos, load_json, now_ms, parse_ping, ping_args, run_command


def _bps_to_mbps(value: Any) -> float | None:
    try:
        return round(float(value) / 1_000_000, 2)
    except (TypeError, ValueError):
        return None


def collect(fast: bool = False) -> dict[str, Any]:
    ts = now_ms()
    if not fast and is_macos():
        code, out, _ = run_command(["networkquality", "-c"], timeout=70)
        data = load_json(out) if code == 0 else {}
        if data:
            return {
                "ts": ts,
                "dl_mbps": _bps_to_mbps(data.get("dl_throughput")),
                "ul_mbps": _bps_to_mbps(data.get("ul_throughput")),
                "rpm_dl": data.get("dl_responsiveness"),
                "rpm_ul": data.get("ul_responsiveness"),
                "ping_avg_ms": None,
                "ping_jitter_ms": None,
                "ping_loss_pct": None,
                "source": "networkquality",
            }

    if not fast and has_command("speedtest"):
        code, out, _ = run_command(["speedtest", "--format=json"], timeout=120)
        data = load_json(out) if code == 0 else {}
        if data:
            download = data.get("download") or {}
            upload = data.get("upload") or {}
            return {
                "ts": ts,
                "dl_mbps": _bps_to_mbps(download.get("bandwidth", 0) * 8 if download.get("bandwidth") else None),
                "ul_mbps": _bps_to_mbps(upload.get("bandwidth", 0) * 8 if upload.get("bandwidth") else None),
                "rpm_dl": None,
                "rpm_ul": None,
                "ping_avg_ms": (data.get("ping") or {}).get("latency"),
                "ping_jitter_ms": (data.get("ping") or {}).get("jitter"),
                "ping_loss_pct": data.get("packetLoss"),
                "source": "speedtest",
            }

    code, out, _ = run_command(ping_args("1.1.1.1", count=5, deadline=2), timeout=12)
    ping = parse_ping(out) if code in (0, 2) else {"avg_ms": None, "jitter_ms": None, "loss_pct": None}
    return {
        "ts": ts,
        "dl_mbps": None,
        "ul_mbps": None,
        "rpm_dl": None,
        "rpm_ul": None,
        "ping_avg_ms": ping["avg_ms"],
        "ping_jitter_ms": ping["jitter_ms"],
        "ping_loss_pct": ping["loss_pct"],
        "source": "ping",
    }
