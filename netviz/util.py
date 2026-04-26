from __future__ import annotations

import json
import platform
import re
import shutil
import statistics
import subprocess
import time
from datetime import datetime, timezone
from typing import Any


def now_ms() -> int:
    return int(time.time() * 1000)


def iso_from_ms(ts: int) -> str:
    return datetime.fromtimestamp(ts / 1000, tz=timezone.utc).isoformat()


def run_command(args: list[str], timeout: float = 5.0) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except FileNotFoundError as exc:
        return 127, "", str(exc)
    except subprocess.TimeoutExpired as exc:
        return 124, exc.stdout or "", exc.stderr or "timeout"


def is_macos() -> bool:
    return platform.system() == "Darwin"


def is_linux() -> bool:
    return platform.system() == "Linux"


def has_command(name: str) -> bool:
    return shutil.which(name) is not None


def ping_args(host: str, count: int = 5, deadline: int = 2) -> list[str]:
    if is_linux():
        return ["ping", "-c", str(count), "-W", str(deadline), host]
    return ["ping", "-c", str(count), "-t", str(deadline), host]


def load_json(text: str) -> dict[str, Any]:
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def mean(values: list[float]) -> float | None:
    return statistics.fmean(values) if values else None


def jitter(values: list[float]) -> float | None:
    if len(values) < 2:
        return 0.0 if values else None
    return statistics.pstdev(values)


PING_TIME_RE = re.compile(r"time[=<]([0-9.]+)\s*ms")
PING_LOSS_RE = re.compile(r"([0-9.]+)% packet loss")


def parse_ping(output: str) -> dict[str, float | None]:
    samples = [float(match.group(1)) for match in PING_TIME_RE.finditer(output)]
    loss_match = PING_LOSS_RE.search(output)
    return {
        "avg_ms": mean(samples),
        "jitter_ms": jitter(samples),
        "loss_pct": float(loss_match.group(1)) if loss_match else None,
    }
