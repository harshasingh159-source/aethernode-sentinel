# AetherNode

**Know every device on your network.** AetherNode finds everything connected to your Wi-Fi/LAN on its own, tells you the moment something new shows up, and lets you mark the devices you recognise as trusted. Anything you haven't vouched for stays in **Need review**.

One Python process does everything (scanning, storage and the web dashboard), with no Node/npm and no admin rights required.

## Quick start

```bash
pip install -r requirements.txt
python -m aethernode --open
```

The dashboard opens at <http://127.0.0.1:8000>. Within ~10 seconds the first scan fills it with every device on your network.

## Using it

- **Need review**: devices you haven't trusted yet. Work through this list:
  - **Trust** devices you recognise.
  - **Rename** gives a device a friendly name (and trusts it).
  - **Forget** removes it; it comes back as *new* if it's seen again.
- **Activity**: a timeline of devices joining, going on/offline, changing IP, and your own changes.
- **Enable alerts**: get a desktop notification whenever a new device joins (while the dashboard tab is open).
- The browser tab title shows how many untrusted devices are online right now.

## How detection works

| Engine | Needs | What it does |
|---|---|---|
| **Sweep** | nothing | Every `--interval` seconds it pings every address on your subnet, then reads the OS's neighbour (ARP) table to learn each device's MAC. New devices are reverse-DNS'd for a hostname. |
| **Live** | scapy + Npcap (Windows) or root (Linux/macOS) | Sniffs ARP traffic so a device appears the instant it talks. If it can't start, AetherNode carries on with sweeps alone. |

A device is marked offline after it's been missing for 3 sweeps (min 3 minutes).

**Vendor names** (e.g. "Apple", "Ubiquiti") come from scapy's built-in manufacturer list. Phones that use a **private/randomized MAC** show a *Private MAC* badge. They have no vendor, and the phone may get a new MAC (and look like a new device) every so often. Turn off "private Wi-Fi address" for your home network on those phones if that gets noisy.

## Options

```
python -m aethernode [--port 8000] [--host 127.0.0.1] [--interval 60]
                     [--subnet 192.168.1.0/24] [--db aethernode.db]
                     [--no-live] [--no-scan] [--open]
```

Use `--host 0.0.0.0` to view the dashboard from your phone on the same network. There's no login, so only do that on a network you trust.

## API

| Method | Path | |
|---|---|---|
| GET | `/api/status` | counts + scanner state |
| GET | `/api/devices` | all devices |
| PATCH | `/api/devices/{mac}` | `{"name": "...", "trusted": true}` |
| DELETE | `/api/devices/{mac}` | forget a device |
| GET | `/api/events?limit=50` | activity log |
| POST | `/api/scan` | sweep now |

## Project layout

```
aethernode/
  __main__.py   CLI entry point
  scanner.py    sweep + live discovery engines
  store.py      SQLite inventory and activity log
  server.py     FastAPI routes, serves static/
  static/       dashboard (plain HTML/CSS/JS)
tests/          python -m unittest
```

> Only monitor networks you own or are allowed to monitor.
