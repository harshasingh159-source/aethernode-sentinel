"""AetherNode REST API — serves the device database to the React dashboard."""
import os
from datetime import datetime, timedelta

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

import database

# A device counts as "online" if the sniffer saw it within this many minutes.
ONLINE_WINDOW_MIN = int(os.environ.get("AETHERNODE_ONLINE_MINUTES", "10"))

app = FastAPI(title="AetherNode Sentinel API", version="1.4")

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("AETHERNODE_CORS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    database.init_db()


class DeviceUpdate(BaseModel):
    mac: str
    hostname: str = Field(min_length=1, max_length=64)


def _cutoff():
    return (datetime.now() - timedelta(minutes=ONLINE_WINDOW_MIN)).strftime("%Y-%m-%d %H:%M:%S")


@app.get("/")
def home():
    return {"status": "online", "system": "AetherNode Sentinel", "version": app.version}


@app.get("/devices")
def read_devices():
    cutoff = _cutoff()
    with database.connect() as conn:
        rows = conn.execute("SELECT * FROM devices ORDER BY last_seen DESC").fetchall()
    return [{**dict(r), "online": bool(r["last_seen"] and r["last_seen"] >= cutoff)} for r in rows]


@app.get("/stats")
def get_stats():
    with database.connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS total, "
            "COALESCE(SUM(status = 'Verified'), 0) AS verified, "
            "COALESCE(SUM(status != 'Verified'), 0) AS unknown, "
            "COALESCE(SUM(last_seen >= ?), 0) AS online FROM devices",
            (_cutoff(),),
        ).fetchone()
    return dict(row)


def _require(conn, mac):
    if not conn.execute("SELECT 1 FROM devices WHERE mac = ?", (mac,)).fetchone():
        raise HTTPException(status_code=404, detail=f"Device {mac} not found")


@app.post("/update_device")
def update_device(data: DeviceUpdate):
    mac, name = data.mac.lower(), data.hostname.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Hostname cannot be blank")
    with database.connect() as conn:
        _require(conn, mac)
        conn.execute("UPDATE devices SET hostname = ?, status = 'Verified' WHERE mac = ?", (name, mac))
    return {"message": f"Device {mac} identified as {name}"}


@app.post("/devices/{mac}/revoke")
def revoke_device(mac: str):
    """Mark a device as Unknown again (e.g. you no longer trust it)."""
    mac = mac.lower()
    with database.connect() as conn:
        _require(conn, mac)
        conn.execute("UPDATE devices SET status = 'Unknown' WHERE mac = ?", (mac,))
    return {"message": f"Device {mac} marked Unknown"}


@app.delete("/devices/{mac}")
def delete_device(mac: str):
    mac = mac.lower()
    with database.connect() as conn:
        _require(conn, mac)
        conn.execute("DELETE FROM devices WHERE mac = ?", (mac,))
    return {"message": f"Device {mac} removed"}


if __name__ == "__main__":
    host = os.environ.get("AETHERNODE_HOST", "127.0.0.1")
    port = int(os.environ.get("AETHERNODE_PORT", "8000"))
    print(f"Starting AetherNode API on http://{host}:{port}  (docs at /docs)")
    uvicorn.run(app, host=host, port=port)
