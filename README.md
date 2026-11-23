# AetherNode

**Know every device on your network.** AetherNode finds everything connected to your Wi-Fi/LAN on its own, tells you the moment something new shows up, and lets you mark the devices you recognise as trusted. Anything you haven't vouched for stays in **Need review**.

One Python process does everything (scanning, storage and the web dashboard), with no Node/npm and no admin rights required.

**What it is not:** AetherNode only lists which devices are on your own network. It does no port scanning, no vulnerability or exploit detection, and it never tries to log in to other devices. The one exception is your router's admin page, and only if you enter its password yourself.

[Code signing policy](CODE_SIGNING_POLICY.md) · [Privacy](#privacy) · [Uninstall](#uninstall) · [License](#license)

## Download (Windows)

1. Download **`AetherNode.exe`** from the [latest release](https://github.com/harshasingh159-source/aethernode-sentinel/releases/latest).
2. Double-click it. The dashboard opens in your browser, and AetherNode keeps running in the background with an icon in the system tray, by the clock (look under the **^** arrow if you don't see it).
3. Windows may show *"Windows protected your PC"*, because the app isn't code-signed yet (see the [code signing policy](CODE_SIGNING_POLICY.md)). Click **More info → Run anyway**. Only do this for a file downloaded from the release page above (you can check it against the SHA-256 listed there).

**Code signing:** AetherNode uses [SignPath Foundation](https://signpath.org) for free code signing of open-source software. The application is in progress, so current releases are still unsigned; see the [code signing policy](CODE_SIGNING_POLICY.md).

There's no installer: AetherNode is a single file, and it doesn't change Windows settings, install services or add itself to startup.

**Tray icon:** click it to open the dashboard. Right-click it for *Open dashboard*, *Open data folder* and *Quit AetherNode*. It turns amber while an untrusted device is online, and Windows notifies you when a new device joins your network.

Your data stays on your PC, in `%LOCALAPPDATA%\AetherNode\` (`aethernode.db`, plus `aethernode.log` for troubleshooting). No account, no cloud. Optional: install [Npcap](https://npcap.com) for instant new-device alerts. Without it, devices still show up within a minute.

Running it again while it's open just brings the dashboard back up.

## Run from source

```bash
pip install -r requirements.txt
python -m aethernode --open
```

Build the .exe yourself (Windows): `powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1`, output in `dist\AetherNode.exe`.

Official releases are built by GitHub Actions straight from this repository (`.github/workflows/release.yml`): pushing a `v*` tag runs the tests, builds the .exe, signs it once code signing is set up, and publishes the release with its SHA-256. Every push to `main` also runs the tests on Windows and Linux.

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

### Cleaning up the router's device list

Routers remember every device that ever joined. In the Router tab, tick devices that are **not connected** (or *Select all not connected*) and press **Remove from router**.

- Connected devices can't be selected, and are re-checked right before each delete.
- Devices are removed **one at a time**: the app re-reads the list, deletes one, and checks that exactly that device disappeared. If anything else vanishes it stops. (Some firmware only honours the first ID of a batch delete and renumbers IDs afterwards.)
- A removed device isn't blocked. If it connects again it simply reappears as new, without any name given on the router.
- The router doesn't record when a device last connected, so there's no automatic "older than a month" option.

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
                     [--router-interval 120] [--open | --no-open]
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
| POST | `/api/router/remove` | `{"macs": [...]}`: make the router forget offline devices |

## Project layout

```
aethernode/
  __main__.py   CLI entry point
  scanner.py    sweep + live discovery engines
  router.py     router admin-page client (device list)
  store.py      SQLite inventory and activity log
  server.py     FastAPI routes, serves static/
  static/       dashboard (plain HTML/CSS/JS)
  tray.py       system-tray front end (Windows .exe)
packaging/      Windows .exe build: build_windows.ps1, icon, version info, license notices
.github/        GitHub Actions: tests on every push, release builds from v* tags
tests/          pip install -r requirements-dev.txt; python -m unittest
```

> Only monitor networks you own or are allowed to monitor.

## Privacy

This program will not transfer any information to other networked systems unless specifically requested by the user or the person installing or operating it. In detail:

- **No telemetry, accounts, ads or update checks.** AetherNode never contacts the internet by itself.
- **Your data stays on your PC,** in `%LOCALAPPDATA%\AetherNode\` (the .exe) or `aethernode.db` in the folder you run it from (source). It holds the device list, the names you give devices, the activity log, and the router login only if you tick *Remember* (stored unencrypted).
- **The dashboard is only reachable from your own PC** (`127.0.0.1`) unless you start it with `--host`.
- **Network traffic it creates, all on your local network:**
  - pings to the addresses of your local network, once a minute
  - reading Windows' own list of nearby devices (the ARP table)
  - reverse-DNS lookups of new devices' local IP addresses. These go to your network's DNS server, which is usually your router.
  - if Npcap is installed, listening for local ARP traffic. Only device addresses are read; nothing is stored beyond the device list.
- **The router integration** contacts only the router address you enter, and only after you sign in. It signs in about every 2 minutes, reads the device list and signs out. It removes devices from the router only when you select them and confirm.
- **Links in the dashboard footer** (source code, license, privacy) open GitHub in your browser only when you click them.

## Uninstall

1. Right-click the tray icon and choose **Quit AetherNode**.
2. Delete `AetherNode.exe`.
3. Delete the folder `%LOCALAPPDATA%\AetherNode` (paste that into Explorer's address bar). It holds your device list and log.

That's everything: AetherNode makes no other changes to your PC. If you installed Npcap for it, you can remove that separately under *Settings → Apps*.

## License

AetherNode's source code is [MIT](LICENSE) licensed: free to use, modify and share.

The Windows .exe also bundles third-party open-source components, each under its own license. They're listed with their full license texts in `THIRD_PARTY_NOTICES.txt`, which is attached to every release and linked from the dashboard footer. Most are MIT, BSD or Apache licensed. **Scapy is GPL-2.0-only** and **pystray is LGPL-3.0**, so if you redistribute the .exe, follow those licenses too. The complete source is in this repository.
