"""Run with:  python -m aethernode   (then open http://127.0.0.1:8000)"""
import argparse
import logging
import webbrowser
from pathlib import Path

import uvicorn

from . import __version__
from .router import RouterLink
from .scanner import Scanner
from .server import create_app
from .store import Store


def main():
    p = argparse.ArgumentParser(prog="aethernode", description="Watch every device on your network.")
    p.add_argument("--host", default="127.0.0.1", help="address to serve the dashboard on (default 127.0.0.1)")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--db", default=str(Path.cwd() / "aethernode.db"), help="database file")
    p.add_argument("--interval", type=int, default=60, help="seconds between network sweeps (default 60)")
    p.add_argument("--subnet", help="CIDR to scan, e.g. 192.168.1.0/24 (default: your /24)")
    p.add_argument("--no-live", action="store_true", help="don't try live ARP sniffing")
    p.add_argument("--no-scan", action="store_true", help="dashboard only, don't scan")
    p.add_argument("--no-router", action="store_true", help="disable the router device-list integration")
    p.add_argument("--router-interval", type=int, default=120, help="seconds between router polls (default 120)")
    p.add_argument("--open", action="store_true", help="open the dashboard in your browser")
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-7s %(message)s", datefmt="%H:%M:%S")
    store = Store(args.db)
    scanner = None
    if not args.no_scan:
        scanner = Scanner(store, interval=max(args.interval, 10), subnet=args.subnet, live=not args.no_live)
        scanner.start()

    router = None if args.no_router else RouterLink(store, interval=max(args.router_interval, 30))

    url = f"http://{'127.0.0.1' if args.host in ('0.0.0.0', '::') else args.host}:{args.port}"
    print(f"\n  AetherNode {__version__}  ->  {url}\n  database: {args.db}\n")
    if args.open:
        webbrowser.open(url)
    uvicorn.run(create_app(store, scanner, router), host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
