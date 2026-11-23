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

## Router device list

The **Router** tab signs in to your router's admin page and shows its list of connected devices. This is the best way to find out whose device is whose, because routers record the name each phone or laptop gives itself (e.g. "Galaxy-S23", "Sams-iPhone"). Those names are copied onto your devices in AetherNode automatically.

- Supported: **Nokia** routers and Wi-Fi Beacons (the "web_whw" admin page).
- Enter the router's admin username and password; they're usually printed on the sticker under the router. They are checked right away and only kept if the router accepts them.
- Tick **Remember** to keep the login across restarts. It is stored unencrypted in `aethernode.db`, so leave it unticked on a shared PC.
- AetherNode signs in, reads the list and signs out again every 2 minutes (`--router-interval`), so it never blocks you from using the router's own admin page. If the router rejects the password, polling stops so it can't trigger the router's lockout.

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
                     [--no-live] [--no-scan] [--no-router]
                     [--router-interval 120] [--open]
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
| GET | `/api/router` | router connection state + its device list |
| PUT | `/api/router` | `{"url", "username", "password", "remember"}`: connect |
| DELETE | `/api/router` | disconnect and forget the login |
| POST | `/api/router/refresh` | re-read the router now |

## Project layout

```
aethernode/
  __main__.py   CLI entry point
  scanner.py    sweep + live discovery engines
  router.py     router admin-page client (device list)
  store.py      SQLite inventory and activity log
  server.py     FastAPI routes, serves static/
  static/       dashboard (plain HTML/CSS/JS)
tests/          python -m unittest
```

> Only monitor networks you own or are allowed to monitor.
