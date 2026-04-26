from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

DEFAULT_DB = Path("metrics.db")


SCHEMA = """
CREATE TABLE IF NOT EXISTS wifi_metrics (
  ts INTEGER PRIMARY KEY,
  iface TEXT, ssid TEXT, bssid TEXT,
  rssi_dbm INTEGER, noise_dbm INTEGER, snr_db INTEGER,
  channel INTEGER, phy_mode TEXT, tx_rate_mbps REAL, local_ip TEXT
);
CREATE TABLE IF NOT EXISTS lan_metrics (
  ts INTEGER PRIMARY KEY,
  gateway_ip TEXT,
  gw_rtt_avg_ms REAL, gw_rtt_jitter_ms REAL, gw_loss_pct REAL,
  arp_entries TEXT
);
CREATE TABLE IF NOT EXISTS wan_metrics (
  ts INTEGER PRIMARY KEY,
  public_ip TEXT, asn TEXT, org TEXT,
  country TEXT, region TEXT, city TEXT,
  loc_lat REAL, loc_lng REAL
);
CREATE TABLE IF NOT EXISTS dns_metrics (
  ts INTEGER, resolver TEXT, hostname TEXT, query_ms REAL,
  PRIMARY KEY (ts, resolver, hostname)
);
CREATE TABLE IF NOT EXISTS quality_metrics (
  ts INTEGER PRIMARY KEY,
  dl_mbps REAL, ul_mbps REAL,
  rpm_dl INTEGER, rpm_ul INTEGER,
  ping_avg_ms REAL, ping_jitter_ms REAL, ping_loss_pct REAL,
  source TEXT
);
CREATE TABLE IF NOT EXISTS traces (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts INTEGER, target TEXT
);
CREATE TABLE IF NOT EXISTS hops (
  trace_id INTEGER, hop_no INTEGER,
  ip TEXT, rtt_ms REAL,
  asn TEXT, org TEXT, country TEXT, lat REAL, lng REAL,
  PRIMARY KEY (trace_id, hop_no),
  FOREIGN KEY (trace_id) REFERENCES traces(id)
);
CREATE TABLE IF NOT EXISTS geo_cache (
  ip TEXT PRIMARY KEY,
  payload TEXT,
  fetched_at INTEGER
);
CREATE TABLE IF NOT EXISTS errors (
  ts INTEGER, collector TEXT, message TEXT
);
CREATE INDEX IF NOT EXISTS idx_wifi_ts ON wifi_metrics(ts DESC);
CREATE INDEX IF NOT EXISTS idx_lan_ts ON lan_metrics(ts DESC);
CREATE INDEX IF NOT EXISTS idx_wan_ts ON wan_metrics(ts DESC);
CREATE INDEX IF NOT EXISTS idx_dns_ts ON dns_metrics(ts DESC);
CREATE INDEX IF NOT EXISTS idx_quality_ts ON quality_metrics(ts DESC);
CREATE INDEX IF NOT EXISTS idx_traces_ts ON traces(ts DESC);
CREATE INDEX IF NOT EXISTS idx_hops_trace_id ON hops(trace_id);
"""


def connect(path: Path | str = DEFAULT_DB) -> sqlite3.Connection:
    db_path = Path(path).expanduser()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def insert_wifi(conn: sqlite3.Connection, row: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO wifi_metrics
        (ts, iface, ssid, bssid, rssi_dbm, noise_dbm, snr_db, channel, phy_mode, tx_rate_mbps, local_ip)
        VALUES (:ts, :iface, :ssid, :bssid, :rssi_dbm, :noise_dbm, :snr_db, :channel, :phy_mode, :tx_rate_mbps, :local_ip)
        """,
        row,
    )


def insert_lan(conn: sqlite3.Connection, row: dict[str, Any]) -> None:
    values = dict(row)
    values["arp_entries"] = json.dumps(values.get("arp_entries") or [], ensure_ascii=False)
    conn.execute(
        """
        INSERT OR REPLACE INTO lan_metrics
        (ts, gateway_ip, gw_rtt_avg_ms, gw_rtt_jitter_ms, gw_loss_pct, arp_entries)
        VALUES (:ts, :gateway_ip, :gw_rtt_avg_ms, :gw_rtt_jitter_ms, :gw_loss_pct, :arp_entries)
        """,
        values,
    )


def insert_wan(conn: sqlite3.Connection, row: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO wan_metrics
        (ts, public_ip, asn, org, country, region, city, loc_lat, loc_lng)
        VALUES (:ts, :public_ip, :asn, :org, :country, :region, :city, :loc_lat, :loc_lng)
        """,
        row,
    )


def insert_dns(conn: sqlite3.Connection, rows: list[dict[str, Any]]) -> None:
    conn.executemany(
        """
        INSERT OR REPLACE INTO dns_metrics (ts, resolver, hostname, query_ms)
        VALUES (:ts, :resolver, :hostname, :query_ms)
        """,
        rows,
    )


def insert_quality(conn: sqlite3.Connection, row: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO quality_metrics
        (ts, dl_mbps, ul_mbps, rpm_dl, rpm_ul, ping_avg_ms, ping_jitter_ms, ping_loss_pct, source)
        VALUES (:ts, :dl_mbps, :ul_mbps, :rpm_dl, :rpm_ul, :ping_avg_ms, :ping_jitter_ms, :ping_loss_pct, :source)
        """,
        row,
    )


def insert_trace(conn: sqlite3.Connection, trace: dict[str, Any]) -> int:
    cur = conn.execute("INSERT INTO traces (ts, target) VALUES (?, ?)", (trace["ts"], trace["target"]))
    trace_id = int(cur.lastrowid)
    for hop in trace.get("hops", []):
        conn.execute(
            """
            INSERT OR REPLACE INTO hops
            (trace_id, hop_no, ip, rtt_ms, asn, org, country, lat, lng)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                trace_id,
                hop.get("hop_no"),
                hop.get("ip"),
                hop.get("rtt_ms"),
                hop.get("asn"),
                hop.get("org"),
                hop.get("country"),
                hop.get("lat"),
                hop.get("lng"),
            ),
        )
    return trace_id


def log_error(conn: sqlite3.Connection, ts: int, collector: str, message: str) -> None:
    conn.execute("INSERT INTO errors (ts, collector, message) VALUES (?, ?, ?)", (ts, collector, message[:1000]))


def latest(conn: sqlite3.Connection, table: str) -> dict[str, Any] | None:
    row = conn.execute(f"SELECT * FROM {table} ORDER BY ts DESC LIMIT 1").fetchone()
    return dict(row) if row else None


def rows_since(conn: sqlite3.Connection, table: str, since_ms: int) -> list[dict[str, Any]]:
    return [dict(row) for row in conn.execute(f"SELECT * FROM {table} WHERE ts >= ? ORDER BY ts ASC", (since_ms,))]
