"""Shared SQLite helpers for AetherNode (used by both sniffer.py and api.py)."""
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime

# Always resolve the DB next to this file, so it works no matter where you launch from.
DB_PATH = os.environ.get(
    "AETHERNODE_DB", os.path.join(os.path.dirname(os.path.abspath(__file__)), "aethernode.db")
)

# column name -> SQL type/default, used both to create the table and to migrate old DBs
COLUMNS = {
    "mac": "TEXT PRIMARY KEY",
    "ip": "TEXT",
    "last_seen": "TEXT",
    "status": "TEXT DEFAULT 'Unknown'",
    "hostname": "TEXT",
    "vendor": "TEXT",
    "first_seen": "TEXT",
}


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


@contextmanager
def connect():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    """Create the devices table, or add any columns missing from an older database."""
    with connect() as conn:
        # WAL lets the sniffer write while the API reads without "database is locked" errors
        conn.execute("PRAGMA journal_mode=WAL")
        cols = ", ".join(f"{name} {spec}" for name, spec in COLUMNS.items())
        conn.execute(f"CREATE TABLE IF NOT EXISTS devices ({cols})")
        existing = {row["name"] for row in conn.execute("PRAGMA table_info(devices)")}
        for name, spec in COLUMNS.items():
            if name not in existing:
                conn.execute(f"ALTER TABLE devices ADD COLUMN {name} {spec}")
        conn.execute("UPDATE devices SET first_seen = last_seen WHERE first_seen IS NULL")


def upsert_device(mac, ip, vendor=None):
    """Record a sighting. Returns True if this MAC has never been seen before."""
    mac = mac.lower()
    ts = now()
    with connect() as conn:
        cur = conn.execute(
            "INSERT OR IGNORE INTO devices (mac, ip, last_seen, first_seen, status, vendor) "
            "VALUES (?, ?, ?, ?, 'Unknown', ?)",
            (mac, ip, ts, ts, vendor),
        )
        is_new = cur.rowcount == 1
        if not is_new:
            conn.execute(
                "UPDATE devices SET ip = ?, last_seen = ?, vendor = COALESCE(vendor, ?) WHERE mac = ?",
                (ip, ts, vendor, mac),
            )
        return is_new


def get_hostname(mac):
    with connect() as conn:
        row = conn.execute("SELECT hostname FROM devices WHERE mac = ?", (mac.lower(),)).fetchone()
        return row["hostname"] if row and row["hostname"] else None


if __name__ == "__main__":
    init_db()
    print(f"[+] Database ready: {DB_PATH}")
