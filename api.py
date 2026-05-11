from fastapi import FastAPI
import sqlite3
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

app = FastAPI()

# 1. MIDDLEWARE SETUP (Crucial for React to talk to Python)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 2. DATA MODELS
class DeviceUpdate(BaseModel):
    mac: str
    hostname: str

# 3. DATABASE HELPER
def get_devices():
    try:
        conn = sqlite3.connect('aethernode.db')
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM devices ORDER BY last_seen DESC")
        rows = c.fetchall()
        conn.close()
        return [dict(row) for row in rows]
    except sqlite3.OperationalError:
        # Returns an empty list if the database/table doesn't exist yet
        return []

# 4. ROUTES
@app.get("/")
def home():
    return {"status": "online", "system": "AetherNode Sentinel"}

@app.get("/devices")
def read_devices():
    # Returning the list directly makes it easier for React to .map()
    return get_devices()

@app.get("/stats")
def get_stats():
    try:
        conn = sqlite3.connect('aethernode.db')
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM devices")
        total = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM devices WHERE status = 'Verified'")
        verified = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM devices WHERE status = 'Unknown'")
        unknown = c.fetchone()[0]
        conn.close()
        return {"total": total, "verified": verified, "unknown": unknown}
    except:
        return {"total": 0, "verified": 0, "unknown": 0}

@app.post("/update_device")
def update_device(data: DeviceUpdate):
    conn = sqlite3.connect('aethernode.db')
    c = conn.cursor()
    c.execute("UPDATE devices SET hostname = ?, status = 'Verified' WHERE mac = ?", 
              (data.hostname, data.mac))
    conn.commit()
    conn.close()
    return {"message": f"Device {data.mac} identified as {data.hostname}"}

# 5. THE ENGINE (This keeps the code running!)
if __name__ == "__main__":
    print("Starting AetherNode API...")
    uvicorn.run(app, host="127.0.0.1", port=8000)