from __future__ import annotations

import re
from typing import Any

from netviz.util import is_linux, is_macos, load_json, now_ms, run_command


def wifi_iface() -> str | None:
    if is_linux():
        return linux_wifi_iface()
    code, out, _ = run_command(["networksetup", "-listallhardwareports"], timeout=5)
    if code != 0:
        return None
    blocks = out.split("\n\n")
    for block in blocks:
        if "Hardware Port: Wi-Fi" in block or "Hardware Port: AirPort" in block:
            match = re.search(r"Device:\s*(\S+)", block)
            return match.group(1) if match else None
    return None


def linux_wifi_iface() -> str | None:
    code, out, _ = run_command(["nmcli", "-t", "-f", "DEVICE,TYPE,STATE", "device", "status"], timeout=3)
    if code == 0:
        for line in out.splitlines():
            parts = line.split(":")
            if len(parts) >= 3 and parts[1] == "wifi" and parts[2] == "connected":
                return parts[0]
        for line in out.splitlines():
            parts = line.split(":")
            if len(parts) >= 2 and parts[1] == "wifi":
                return parts[0]

    code, out, _ = run_command(["iw", "dev"], timeout=3)
    if code == 0:
        match = re.search(r"Interface\s+(\S+)", out)
        return match.group(1) if match else None
    return None


def _first_airport_interface(data: dict[str, Any]) -> dict[str, Any]:
    items = data.get("SPAirPortDataType") or []
    for item in items:
        interfaces = item.get("spairport_airport_interfaces") or []
        if interfaces:
            return interfaces[0]
    return {}


def _parse_channel(value: Any) -> int | None:
    if value is None:
        return None
    match = re.search(r"\d+", str(value))
    return int(match.group(0)) if match else None


def _channel_from_freq(freq_mhz: int | None) -> int | None:
    if not freq_mhz:
        return None
    if 2412 <= freq_mhz <= 2484:
        return 14 if freq_mhz == 2484 else (freq_mhz - 2407) // 5
    if 5000 <= freq_mhz <= 5895:
        return (freq_mhz - 5000) // 5
    if 5955 <= freq_mhz <= 7115:
        return (freq_mhz - 5950) // 5
    return None


def collect_linux(ts: int, iface: str | None) -> dict[str, Any]:
    local_ip = None
    ssid = None
    bssid = None
    rssi = None
    channel = None
    tx_rate = None

    if iface:
        code, out, _ = run_command(["ip", "-4", "-o", "addr", "show", "dev", iface], timeout=2)
        if code == 0:
            match = re.search(r"\binet\s+([0-9.]+)/", out)
            local_ip = match.group(1) if match else None

        code, out, _ = run_command(["iw", "dev", iface, "link"], timeout=3)
        if code == 0:
            bssid_match = re.search(r"Connected to\s+([0-9a-f:]+)", out, re.I)
            ssid_match = re.search(r"SSID:\s*(.+)", out)
            freq_match = re.search(r"freq:\s*(\d+)", out)
            signal_match = re.search(r"signal:\s*(-?\d+)", out)
            tx_match = re.search(r"tx bitrate:\s*([0-9.]+)", out)
            bssid = bssid_match.group(1) if bssid_match else None
            ssid = ssid_match.group(1).strip() if ssid_match else None
            channel = _channel_from_freq(int(freq_match.group(1))) if freq_match else None
            rssi = int(signal_match.group(1)) if signal_match else None
            tx_rate = float(tx_match.group(1)) if tx_match else None

        if not ssid:
            code, out, _ = run_command(["nmcli", "-t", "-f", "ACTIVE,SSID,BSSID,CHAN,RATE,SIGNAL", "dev", "wifi"], timeout=5)
            if code == 0:
                for line in out.splitlines():
                    parts = line.split(":")
                    if parts and parts[0] == "yes":
                        ssid = parts[1] if len(parts) > 1 else None
                        bssid = ":".join(parts[2:8]) if len(parts) >= 8 else bssid
                        channel = int(parts[8]) if len(parts) > 8 and parts[8].isdigit() else channel
                        break

    return {
        "ts": ts,
        "iface": iface,
        "ssid": ssid,
        "bssid": bssid,
        "rssi_dbm": rssi,
        "noise_dbm": None,
        "snr_db": None,
        "channel": channel,
        "phy_mode": "Wi-Fi",
        "tx_rate_mbps": tx_rate,
        "local_ip": local_ip,
    }


def collect() -> dict[str, Any]:
    ts = now_ms()
    iface = wifi_iface()
    if is_linux():
        return collect_linux(ts, iface)

    local_ip = None
    ssid = None
    bssid = None
    rssi = None
    noise = None
    channel = None
    phy_mode = None
    tx_rate = None

    if iface and is_macos():
        code, out, _ = run_command(["ipconfig", "getifaddr", iface], timeout=2)
        local_ip = out if code == 0 and out else None
        code, out, _ = run_command(["networksetup", "-getairportnetwork", iface], timeout=3)
        if code == 0:
            match = re.search(r"Current Wi-Fi Network:\s*(.+)$", out)
            ssid = match.group(1).strip() if match else None

    code, out, _ = run_command(["system_profiler", "SPAirPortDataType", "-json"], timeout=12)
    if code == 0 and out:
        interface = _first_airport_interface(load_json(out))
        current = interface.get("spairport_current_network_information") or {}
        if isinstance(current, dict):
            if not ssid:
                ssid = current.get("_name") or current.get("spairport_network_name")
            bssid = current.get("spairport_bssid") or current.get("BSSID")
            rssi = current.get("spairport_signal_noise")
            if isinstance(rssi, str):
                match = re.search(r"(-?\d+)\s*dBm", rssi)
                rssi = int(match.group(1)) if match else None
            noise = current.get("spairport_noise")
            if isinstance(noise, str):
                match = re.search(r"(-?\d+)\s*dBm", noise)
                noise = int(match.group(1)) if match else None
            channel = _parse_channel(current.get("spairport_channel"))
            phy_mode = current.get("spairport_phymode") or current.get("spairport_network_phymode")
            tx_rate = current.get("spairport_transmit_rate")
            try:
                tx_rate = float(tx_rate) if tx_rate is not None else None
            except (TypeError, ValueError):
                tx_rate = None

    snr = rssi - noise if isinstance(rssi, int) and isinstance(noise, int) else None
    return {
        "ts": ts,
        "iface": iface,
        "ssid": ssid,
        "bssid": bssid,
        "rssi_dbm": rssi,
        "noise_dbm": noise,
        "snr_db": snr,
        "channel": channel,
        "phy_mode": phy_mode,
        "tx_rate_mbps": tx_rate,
        "local_ip": local_ip,
    }
