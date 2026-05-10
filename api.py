from fastapi import FastAPI
import sqlite3
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI()

# 1. MIDDLEWARE SETUP
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

# 3. HELPER FUNCTIONS
def get_devices():
    conn = sqlite3.connect('aethernode.db')
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM devices ORDER BY last_seen DESC")
    rows = c.fetchall()
    conn.close()
    return [dict(row) for row in rows]

# 4. ROUTES (GET)
@app.get("/")
def home():
    return {"message": "AetherNode API is Online"}

@app.get("/devices")
def read_devices():
    return {"devices": get_devices()}

# 5. ROUTES (POST)
@app.post("/update_device")
def update_device(data: DeviceUpdate):
    conn = sqlite3.connect('aethernode.db')
    c = conn.cursor()
    # Update the status to 'Verified' and set the nickname
    c.execute("UPDATE devices SET hostname = ?, status = 'Verified' WHERE mac = ?", 
              (data.hostname, data.mac))
    conn.commit()
    conn.close()
    return {"message": f"Device {data.mac} identified as {data.hostname}"}
@app.get("/stats")
def get_stats():
    conn = sqlite3.connect('aethernode.db')
    c = conn.cursor()
    
    # Get counts for different categories
    c.execute("SELECT COUNT(*) FROM devices")
    total = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM devices WHERE status = 'Verified'")
    verified = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM devices WHERE status = 'Unknown'")
    unknown = c.fetchone()[0]
    
    conn.close()
    return {
        "total": total,
        "verified": verified,
        "unknown": unknown
    }