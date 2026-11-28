"""Create a database full of made-up devices, for screenshots and demos.

    python packaging/make_demo_db.py demo.db
    python -m aethernode --demo --db demo.db --no-tray

Every name and IP here is fictional and the MACs are made up (only their first half is a real
manufacturer prefix), so screenshots never expose a real network.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from aethernode.store import Store  # noqa: E402

NOW = time.time()
H = 3600
# mac, ip, hostname, vendor, name, trusted, is_self, online, first_seen_ago, last_seen_ago
DEVICES = [
    ("8c:8d:28:4a:10:01", "192.168.1.10", "DESKTOP-HOME", "Intel Corporate", None, True, True, True, 30 * 24 * H, 0),
    ("50:c7:bf:4a:10:02", "192.168.1.1", None, "TP-Link Technologies", "Router", True, False, True, 30 * 24 * H, 0),
    ("0a:00:5e:10:00:03", "192.168.1.21", "Sams-iPhone", None, "Sam's iPhone", True, False, True, 20 * 24 * H, 60),
    ("8c:79:f5:4a:10:04", "192.168.1.30", "LivingRoom-TV", "Samsung Electronics", "Living room TV", True, False, True, 25 * 24 * H, 120),
    ("3c:52:82:4a:10:05", "192.168.1.42", "HP-LaserJet", "HP Inc.", "Printer", True, False, False, 25 * 24 * H, 3 * H),
    ("0e:00:5e:10:00:06", "192.168.1.55", "Galaxy-A54", None, None, False, False, True, 4 * 60, 30),
    ("24:0a:c4:4a:10:07", "192.168.1.61", None, "Espressif Inc.", None, False, False, True, 2 * H, 45),
    ("12:00:5e:10:00:08", "192.168.1.73", "Alexs-MacBook", None, "Alex's laptop", True, False, False, 12 * 24 * H, 9 * H),
]


def main(path):
    p = Path(path)
    for f in (p, p.with_name(p.name + "-journal")):
        if f.exists():
            f.unlink()
    store = Store(str(p))
    for mac, ip, host, vendor, name, trusted, me, online, first_ago, last_ago in DEVICES:
        store.observe(mac, ip, hostname=host, vendor=vendor, is_self=me, now=NOW - first_ago)
        store.observe(mac, ip, hostname=host, now=NOW - last_ago)
        store.update(mac, name=name, trusted=trusted if not me else None)
        if not online:
            store.expire(older_than=NOW - last_ago + 1, now=NOW - last_ago + 600)
    # Renames/trusts were logged "now": move them to shortly after each device first appeared,
    # then renumber all events in time order so the activity feed reads like a real history.
    db = store._db
    with db:
        db.execute("UPDATE events SET ts = (SELECT first_seen + 600 FROM devices d WHERE d.mac = events.mac) "
                   "WHERE kind IN ('renamed', 'trusted')")
        rows = db.execute("SELECT ts, kind, mac, detail FROM events ORDER BY ts").fetchall()
        db.execute("DELETE FROM events")
        db.execute("DELETE FROM sqlite_sequence WHERE name = 'events'")
        db.executemany("INSERT INTO events (ts, kind, mac, detail) VALUES (?, ?, ?, ?)", [tuple(r) for r in rows])
    store.close()
    print(f"wrote {p} with {len(DEVICES)} demo devices")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "demo.db")
