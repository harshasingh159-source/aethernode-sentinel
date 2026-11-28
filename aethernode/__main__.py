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
    p.add_argument("--demo", action="store_true",
                   help="screenshot/demo mode: no scanning or router, but a realistic scanner status "
                        "(pair with a database from packaging/make_demo_db.py)")
    p.add_argument("--no-router", action="store_true", help="disable the router device-list integration")
    p.add_argument("--router-interval", type=int, default=120, help="seconds between router polls (default 120)")
    p.add_argument("--open", action="store_true", default=FROZEN,
                   help="open the dashboard in your browser (default for the .exe)")
    p.add_argument("--no-open", dest="open", action="store_false", help="don't open the browser")
    p.add_argument("--tray", action=argparse.BooleanOptionalAction, default=FROZEN,
                   help="run in the background with a system-tray icon (default for the .exe)")
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

    data_dir = Path(args.db).resolve().parent
    if args.tray:
        # No console in the windowed .exe: send all output to a log file next to the database.
        log_path = data_dir / "aethernode.log"
        if log_path.exists() and log_path.stat().st_size > 2_000_000:
            log_path.replace(log_path.with_suffix(".log.old"))
        stream = open(log_path, "a", encoding="utf-8", buffering=1)  # noqa: SIM115 - lives for the process
        sys.stdout = sys.stdout or stream
        sys.stderr = sys.stderr or stream
        logging.basicConfig(level=logging.INFO, stream=stream,
                            format="%(asctime)s  %(levelname)-7s %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    else:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-7s %(message)s", datefmt="%H:%M:%S")

    try:
        run(args, port, local, data_dir)
    except Exception as e:
        logging.exception("AetherNode failed to start")
        if args.tray:
            show_error(f"AetherNode couldn't start:\n\n{e}\n\nDetails are in {data_dir / 'aethernode.log'}")
        raise


class DemoScanner:
    """Stands in for the scanner in --demo mode: never touches the network, but reports a
    plausible status so screenshots look like a normal running app."""

    def __init__(self, store):
        self.store = store
        self.started = __import__("time").time()

    @property
    def state(self):
        import time
        now = time.time()
        since = (now - self.started) % 60
        return {"subnet": "192.168.1.0/24", "self_ip": "192.168.1.10", "scanning": False,
                "last_scan": now - since - 8, "last_scan_found": self.store.counts()["online"],
                "next_scan": now + 60 - since, "live": "on", "error": None, "interval": 60}

    def scan_now(self):
        pass

    def stop(self):
        pass


def show_error(text):
    if os.name == "nt":
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, text, "AetherNode", 0x10)


def run(args, port, local, data_dir):
    # heavy imports only once we know we're starting
    import uvicorn

    from .router import RouterLink
    from .scanner import Scanner
    from .server import create_app
    from .store import Store

    store = Store(args.db)
    scanner = None
    if args.demo:
        scanner = DemoScanner(store)
    elif not args.no_scan:
        scanner = Scanner(store, interval=max(args.interval, 10), subnet=args.subnet, live=not args.no_live)
        scanner.start()

    router = None if (args.no_router or args.demo) else RouterLink(store, interval=max(args.router_interval, 30))

    url = f"http://{local}:{port}"
    app = create_app(store, scanner, router)
    logging.info("AetherNode %s at %s (database %s)", __version__, url, args.db)

    if not args.tray:
        print(f"\n  AetherNode {__version__}  ->  {url}\n  database: {args.db}\n")
        if args.open:
            webbrowser.open(url)
        uvicorn.run(app, host=args.host, port=port, log_level="warning")
        return

    # Tray mode: web server in a background thread, tray icon on the main thread.
    import threading

    from .tray import Tray
    server = uvicorn.Server(uvicorn.Config(app, host=args.host, port=port, log_level="warning", log_config=None))
    web = threading.Thread(target=server.run, name="web", daemon=True)
    web.start()
    for _ in range(100):  # wait up to ~10 s for the dashboard to come up
        if server.started or not web.is_alive():
            break
        threading.Event().wait(0.1)
    if not server.started:
        raise RuntimeError(f"the dashboard server didn't start on port {port}")
    if args.open:
        webbrowser.open(url)

    def quit_app():
        logging.info("Quit from tray")
        if scanner:
            scanner.stop()
        server.should_exit = True

    Tray(url, store, data_dir, quit_app, scanner=scanner).run()
    web.join(timeout=5)


if __name__ == "__main__":
    main()
