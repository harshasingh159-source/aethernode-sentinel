# 📡 AETHER_NODE_SENTINEL V1.4

> **Status:** [ SYSTEM_OPERATIONAL ]  
> **Network:** [ WORLDLINK_SECURED ]  
> **Target:** [ INTRUSION_DETECTION_&_MAPPING ]

AetherNode is a custom-built network security engine designed to unmask every device on a local network. Using low-level ARP sniffing and a React-based command center, it identifies "Unknown" visitors and alerts the administrator to potential unauthorized access.

---

## 🛠️ THE ARCHITECTURE
AetherNode works in three synchronized layers:

1.  **THE SENSOR (Python/Scapy):** Stealthily monitors the network for ARP packets and identifies hardware "fingerprints."
2.  **THE BRAIN (FastAPI/SQLite):** Stores device history and manages the "Verified" status of known hardware like your Laptop, Phone, and Worldlink Router.
3.  **THE HUD (React):** A real-time dashboard with "Matrix" styling that pulses red when an unverified device is detected.

---

## 🚀 FEATURES
* **Passive + active detection:** listens to all ARP traffic, and with `--scan` sweeps the subnet so quiet devices show up too.
* **Hardware fingerprinting:** vendor lookup from the MAC (e.g. Nokia, Dell, Apple); flags randomized/private MACs.
* **Intruder alerts:** red-pulse rows for unverified devices, alert count in the browser tab title.
* **Live status:** online indicator + "last seen" per device; counters for Total / Online / Verified / Unknown.
* **Device management:** identify/rename inline, revoke trust, or remove a device.
* **Search & filters:** filter by name, MAC, IP, vendor; ALL / ONLINE / UNKNOWN views.

---

## 💻 TECH STACK
* **Language:** Python 3.10+
* **Sensor:** Scapy
* **Backend:** FastAPI + SQLite3
* **Frontend:** React (Create React App)

---

## 🚦 GETTING STARTED

### 1. Install
```bash
pip install -r requirements.txt
cd frontend && npm install
```
On **Windows**, sniffing also requires [Npcap](https://npcap.com) (tick "WinPcap API-compatible mode").

### 2. Run (three terminals, from the repo root)
```bash
# Sensor — needs Administrator / sudo
python sniffer.py --scan

# API — http://127.0.0.1:8000  (interactive docs at /docs)
python api.py

# Dashboard — http://localhost:3000
cd frontend && npm start
```
The database (`aethernode.db`) is created/migrated automatically next to the scripts.

### Configuration
| Variable | Where | Default |
|---|---|---|
| `REACT_APP_API_URL` | `frontend/.env.local` | `http://127.0.0.1:8000` (set to your tunnel URL to view remotely) |
| `AETHERNODE_HOST` / `AETHERNODE_PORT` | API | `127.0.0.1` / `8000` |
| `AETHERNODE_ONLINE_MINUTES` | API | `10` — how recently a device must be seen to count as online |
| `AETHERNODE_DB` | sensor + API | `./aethernode.db` |

Sniffer options: `--iface NAME`, `--scan`, `--interval SECONDS`.

### API
| Method | Path | |
|---|---|---|
| GET | `/devices` | all devices (with `online` flag) |
| GET | `/stats` | totals |
| POST | `/update_device` | `{mac, hostname}` → names + verifies a device |
| POST | `/devices/{mac}/revoke` | mark a device Unknown again |
| DELETE | `/devices/{mac}` | forget a device |

> ⚠️ Only monitor networks you own or are authorized to monitor.
