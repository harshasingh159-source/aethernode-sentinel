# 📡 AETHER_NODE_SENTINEL V1.3

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
* **Zero-Latency Detection:** Sees new devices the moment they join.
* **Hardware Fingerprinting:** Automatically identifies manufacturers (e.g., Nokia, Dell, Apple).
* **Intruder Alerts:** Visual red-pulse animation for unverified MAC addresses.
* **Network Stats:** Live counters for Active vs. Known devices.
* **Kali Linux Ready:** Optimized for execution in Linux environments for advanced sniffing.

---

## 💻 TECH STACK
* **Language:** Python 3.10+
* **Library:** Scapy (Packet Manipulation)
* **Backend:** FastAPI
* **Frontend:** React.js (Custom Terminal UI)
* **Database:** SQLite3

---

## 🚦 GETTING STARTED

### 1. The Backend
```bash
cd backend
pip install -r requirements.txt
python sniffer.py