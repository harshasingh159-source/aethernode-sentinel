"""Persistent device inventory + activity log, backed by SQLite."""
import json
import sqlite3
import threading
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS devices (
    mac        TEXT PRIMARY KEY,
    ip         TEXT,
    hostname   TEXT,
    vendor     TEXT,
    name       TEXT,
    trusted    INTEGER NOT NULL DEFAULT 0,
    is_self    INTEGER NOT NULL DEFAULT 0,
    online     INTEGER NOT NULL DEFAULT 1,
    first_seen REAL NOT NULL,
    last_seen  REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    ts     REAL NOT NULL,
    kind   TEXT NOT NULL,      -- joined | online | offline | ip_changed | trusted | untrusted | renamed | forgotten
    mac    TEXT NOT NULL,
    detail TEXT
);
CREATE INDEX IF NOT EXISTS events_by_time ON events (ts DESC);
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""


class Store:
    """Thread-safe: the scanner threads and the web server share one instance."""

    def __init__(self, path):
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        with self._lock, self._db:
            self._db.executescript(SCHEMA)

    def close(self):
        self._db.close()

    # ---- writes from the scanner ----

    def observe(self, mac, ip, *, hostname=None, vendor=None, is_self=False, now=None):
        """Record that `mac` is present at `ip`. Returns 'joined', 'online' or None."""
        now = now or time.time()
        with self._lock, self._db:
            row = self._db.execute("SELECT * FROM devices WHERE mac = ?", (mac,)).fetchone()
            if row is None:
                self._db.execute(
                    "INSERT INTO devices (mac, ip, hostname, vendor, is_self, trusted, first_seen, last_seen)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (mac, ip, hostname, vendor, int(is_self), int(is_self), now, now),
                )
                self._log(now, "joined", mac, ip)
                return "joined"

            self._db.execute(
                "UPDATE devices SET ip = ?, last_seen = ?, online = 1,"
                " hostname = COALESCE(?, hostname), vendor = COALESCE(vendor, ?),"
                " is_self = MAX(is_self, ?) WHERE mac = ?",
                (ip, now, hostname, vendor, int(is_self), mac),
            )
            if is_self and not row["is_self"]:  # first identified as this PC: vouch for it
                self._db.execute("UPDATE devices SET trusted = 1 WHERE mac = ?", (mac,))
            if row["ip"] != ip:
                self._log(now, "ip_changed", mac, f"{row['ip']} → {ip}")
            if not row["online"]:
                self._log(now, "online", mac, ip)
                return "online"
            return None

    def expire(self, older_than, now=None):
        """Mark devices not seen since `older_than` as offline. Returns how many changed."""
        now = now or time.time()
        with self._lock, self._db:
            gone = self._db.execute(
                "SELECT mac FROM devices WHERE online = 1 AND last_seen < ?", (older_than,)
            ).fetchall()
            for r in gone:
                self._db.execute("UPDATE devices SET online = 0 WHERE mac = ?", (r["mac"],))
                self._log(now, "offline", r["mac"], None)
            return len(gone)

    # ---- writes from the user ----

    def update(self, mac, *, name=None, trusted=None):
        with self._lock, self._db:
            row = self._db.execute("SELECT * FROM devices WHERE mac = ?", (mac,)).fetchone()
            if row is None:
                return None
            now = time.time()
            if name is not None:
                name = name.strip() or None
                if name != row["name"]:
                    self._db.execute("UPDATE devices SET name = ? WHERE mac = ?", (name, mac))
                    self._log(now, "renamed", mac, name)
            if trusted is not None and bool(trusted) != bool(row["trusted"]):
                self._db.execute("UPDATE devices SET trusted = ? WHERE mac = ?", (int(trusted), mac))
                self._log(now, "trusted" if trusted else "untrusted", mac, None)
        return self.device(mac)

    def forget(self, mac):
        with self._lock, self._db:
            cur = self._db.execute("DELETE FROM devices WHERE mac = ?", (mac,))
            if cur.rowcount:
                self._log(time.time(), "forgotten", mac, None)
            return cur.rowcount > 0

    def name_from_router(self, mac, name):
        """Router-reported names beat reverse DNS; only applied to devices we already know."""
        with self._lock, self._db:
            self._db.execute("UPDATE devices SET hostname = ? WHERE mac = ?", (name, mac))

    # ---- settings ----

    def get_setting(self, key, default=None):
        with self._lock:
            row = self._db.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return json.loads(row["value"]) if row else default

    def set_setting(self, key, value):
        with self._lock, self._db:
            if value is None:
                self._db.execute("DELETE FROM settings WHERE key = ?", (key,))
            else:
                self._db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                                 (key, json.dumps(value)))

    # ---- reads ----

    def device(self, mac):
        with self._lock:
            row = self._db.execute("SELECT * FROM devices WHERE mac = ?", (mac,)).fetchone()
        return _device(row) if row else None

    def devices(self):
        with self._lock:
            rows = self._db.execute(
                "SELECT * FROM devices ORDER BY trusted ASC, online DESC, last_seen DESC"
            ).fetchall()
        return [_device(r) for r in rows]

    def events(self, limit=50):
        with self._lock:
            rows = self._db.execute(
                "SELECT e.*, COALESCE(d.name, d.hostname, d.vendor) AS label"
                " FROM events e LEFT JOIN devices d ON d.mac = e.mac"
                " ORDER BY e.id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def counts(self):
        with self._lock:
            r = self._db.execute(
                "SELECT COUNT(*) AS total,"
                " COALESCE(SUM(online), 0) AS online,"
                " COALESCE(SUM(trusted), 0) AS trusted,"
                " COALESCE(SUM(trusted = 0), 0) AS untrusted,"
                " COALESCE(SUM(trusted = 0 AND online = 1), 0) AS untrusted_online"
                " FROM devices"
            ).fetchone()
        return dict(r)

    def _log(self, ts, kind, mac, detail):
        self._db.execute(
            "INSERT INTO events (ts, kind, mac, detail) VALUES (?, ?, ?, ?)", (ts, kind, mac, detail)
        )


def _device(row):
    d = dict(row)
    for key in ("trusted", "is_self", "online"):
        d[key] = bool(d[key])
    d["private_mac"] = is_private_mac(d["mac"])
    return d


def is_private_mac(mac):
    """Phones/laptops using a randomized "private Wi-Fi address" set the locally-administered bit."""
    return bool(int(mac[:2], 16) & 0x02)
