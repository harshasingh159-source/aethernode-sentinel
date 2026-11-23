"""Run with:  python -m aethernode   (then open http://127.0.0.1:8000)

The Windows .exe runs this same entry point; when frozen it stores its database in
%LOCALAPPDATA%\\AetherNode and opens the dashboard in the browser automatically.
"""
import argparse
import json
import logging
import os
import socket
import sys
import urllib.request
import webbrowser
from pathlib import Path

from . import __version__

FROZEN = getattr(sys, "frozen", False)  # running as the packaged .exe


def default_db():
    if FROZEN:
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "AetherNode"
        base.mkdir(parents=True, exist_ok=True)
        return str(base / "aethernode.db")
    return str(Path.cwd() / "aethernode.db")


def already_running(host, port):
    """True if an AetherNode dashboard is already answering on host:port."""
    try:
        with urllib.request.urlopen(f"http://{host}:{port}/api/status", timeout=1.5) as r:
            return "counts" in json.loads(r.read().decode())
    except Exception:
        return False


def port_free(host, port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((host, port))
            return True
        except OSError:
            return False


def main():
    p = argparse.ArgumentParser(prog="aethernode", description="Watch every device on your network.")
    p.add_argument("--host", default="127.0.0.1", help="address to serve the dashboard on (default 127.0.0.1)")
    p.add_argument("--port", type=int, default=8000, help="dashboard port (default 8000; next free one if busy)")
    p.add_argument("--db", default=default_db(), help="database file")
    p.add_argument("--interval", type=int, default=60, help="seconds between network sweeps (default 60)")
    p.add_argument("--subnet", help="CIDR to scan, e.g. 192.168.1.0/24 (default: your /24)")
    p.add_argument("--no-live", action="store_true", help="don't try live ARP sniffing")
    p.add_argument("--no-scan", action="store_true", help="dashboard only, don't scan")
    p.add_argument("--no-router", action="store_true", help="disable the router device-list integration")
    p.add_argument("--router-interval", type=int, default=120, help="seconds between router polls (default 120)")
    p.add_argument("--open", action="store_true", default=FROZEN,
                   help="open the dashboard in your browser (default for the .exe)")
    p.add_argument("--no-open", dest="open", action="store_false", help="don't open the browser")
    p.add_argument("--version", action="version", version=f"AetherNode {__version__}")
    args = p.parse_args()

    local = "127.0.0.1" if args.host in ("0.0.0.0", "::") else args.host
    if already_running(local, args.port):
        # e.g. the .exe was double-clicked again: just show the running dashboard
        print(f"AetherNode is already running at http://{local}:{args.port}")
        if args.open:
            webbrowser.open(f"http://{local}:{args.port}")
        return
    port = args.port
    while not port_free(args.host, port) and port < args.port + 20:
        port += 1

    # heavy imports only once we know we're starting
    import uvicorn

    from .router import RouterLink
    from .scanner import Scanner
    from .server import create_app
    from .store import Store

    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-7s %(message)s", datefmt="%H:%M:%S")
    store = Store(args.db)
    scanner = None
    if not args.no_scan:
        scanner = Scanner(store, interval=max(args.interval, 10), subnet=args.subnet, live=not args.no_live)
        scanner.start()

    router = None if args.no_router else RouterLink(store, interval=max(args.router_interval, 30))

    url = f"http://{local}:{port}"
    print(f"\n  AetherNode {__version__}  ->  {url}\n  database: {args.db}\n")
    if FROZEN:
        print("  Keep this window open while you use AetherNode. Close it to stop.\n")
    if args.open:
        webbrowser.open(url)
    uvicorn.run(create_app(store, scanner, router), host=args.host, port=port, log_level="warning")


if __name__ == "__main__":
    main()
