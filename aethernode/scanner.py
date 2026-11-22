"""Device discovery.

Sweep engine (works for any user, no admin):
    ping every host on the subnet so the OS learns their MACs, then read the OS
    neighbour (ARP) table. Also reverse-DNS each new device to get its hostname.

Live engine (optional; needs scapy + Npcap on Windows, root on Linux/macOS):
    sniff ARP traffic so a device appears the moment it talks, between sweeps.
"""
import ipaddress
import logging
import platform
import re
import socket
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

log = logging.getLogger("aethernode.scanner")

IS_WINDOWS = platform.system() == "Windows"
_NO_WINDOW = 0x08000000 if IS_WINDOWS else 0  # CREATE_NO_WINDOW: no console flash per ping

_MAC = re.compile(r"(?<![0-9a-f])([0-9a-f]{1,2}[:-]){5}[0-9a-f]{1,2}(?![0-9a-f])", re.I)
_IP = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")


# ---------------------------------------------------------------- helpers

def normalize_mac(raw):
    parts = re.split(r"[:-]", raw.strip().lower())
    return ":".join(p.zfill(2) for p in parts)


def is_real_device(mac, ip):
    if mac in ("00:00:00:00:00:00", "ff:ff:ff:ff:ff:ff") or int(mac[:2], 16) & 0x01:
        return False  # empty, broadcast or multicast MAC
    addr = ipaddress.ip_address(ip)
    return not (addr.is_multicast or addr.is_loopback or addr.is_unspecified or addr.is_link_local)


def parse_neighbour_table(text):
    """Extract (mac, ip) pairs from `arp -a` (Windows/macOS) or `ip neigh` output."""
    pairs = []
    for line in text.splitlines():
        if any(bad in line.upper() for bad in ("INCOMPLETE", "FAILED")):
            continue
        ip, mac = _IP.search(line), _MAC.search(line)
        if ip and mac:
            pairs.append((normalize_mac(mac.group(0)), ip.group(0)))
    return pairs


def read_neighbour_table():
    if IS_WINDOWS:
        cmds = [["arp", "-a"]]
    else:
        proc = Path("/proc/net/arp")
        if proc.exists():  # Linux: no subprocess needed
            return parse_neighbour_table(proc.read_text())
        cmds = [["ip", "neigh"], ["arp", "-an"]]
    for cmd in cmds:
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=10, creationflags=_NO_WINDOW)
            return parse_neighbour_table(out.stdout)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    return []


def local_ip():
    # connect() on a UDP socket sends no packets; it just picks the outbound interface.
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]


def ping(ip):
    cmd = ["ping", "-n", "1", "-w", "600", ip] if IS_WINDOWS else ["ping", "-c", "1", "-W", "1", ip]
    try:
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       timeout=5, creationflags=_NO_WINDOW)
    except subprocess.TimeoutExpired:
        pass


def reverse_dns(ip):
    try:
        name = socket.gethostbyaddr(ip)[0]
    except OSError:
        return None
    return None if not name or name == ip else name.rstrip(".")


try:  # scapy is optional: it gives us vendor names and live sniffing
    from scapy.all import conf as _scapy_conf  # noqa: F401
    HAVE_SCAPY = True
except Exception:  # pragma: no cover - depends on environment
    HAVE_SCAPY = False


def vendor_of(mac):
    if int(mac[:2], 16) & 0x02 or not HAVE_SCAPY:
        return None  # randomized MACs carry no vendor
    try:
        short, long = _scapy_conf.manufdb.lookup(mac)
        return (long or short) if short and short != mac else None
    except Exception:
        return None


def own_mac():
    if HAVE_SCAPY:
        try:
            from scapy.all import get_if_hwaddr
            return normalize_mac(get_if_hwaddr(_scapy_conf.iface))
        except Exception:
            pass
    return None


# ---------------------------------------------------------------- scanner

class Scanner:
    def __init__(self, store, *, interval=60, subnet=None, live=True, offline_after=None):
        self.store = store
        self.interval = interval
        self.offline_after = offline_after or max(3 * interval, 180)
        self.live_wanted = live
        self._subnet = subnet
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._dns = ThreadPoolExecutor(max_workers=8, thread_name_prefix="dns")
        self.state = {
            "subnet": None, "self_ip": None, "scanning": False, "last_scan": None,
            "last_scan_found": 0, "next_scan": None, "live": "off", "error": None,
            "interval": interval,
        }

    # -- lifecycle
    def start(self):
        threading.Thread(target=self._loop, name="sweep", daemon=True).start()
        if self.live_wanted:
            threading.Thread(target=self._live, name="live", daemon=True).start()

    def stop(self):
        self._stop.set()
        self._wake.set()

    def scan_now(self):
        self._wake.set()

    # -- recording
    def _record(self, mac, ip, *, is_self=False, hostname=None):
        if not is_real_device(mac, ip):
            return
        result = self.store.observe(mac, ip, vendor=vendor_of(mac), is_self=is_self, hostname=hostname)
        if result == "joined":
            log.warning("NEW DEVICE %s at %s", mac, ip)
            if not hostname:
                self._dns.submit(self._resolve, mac, ip)
        elif result == "online":
            log.info("back online: %s at %s", mac, ip)

    def _resolve(self, mac, ip):
        name = reverse_dns(ip)
        if name:
            self.store.observe(mac, ip, hostname=name)

    # -- sweep engine
    def _network(self):
        me = local_ip()
        net = ipaddress.ip_network(self._subnet or f"{me}/24", strict=False)
        if net.num_addresses > 1024:
            raise ValueError(f"subnet {net} is too large to sweep (max /22)")
        return me, net

    def sweep(self):
        me, net = self._network()
        self.state.update(subnet=str(net), self_ip=me, scanning=True, error=None)
        try:
            with ThreadPoolExecutor(max_workers=64, thread_name_prefix="ping") as pool:
                list(pool.map(ping, (str(h) for h in net.hosts() if str(h) != me)))
            found = 0
            mine = own_mac()
            if mine:
                self._record(mine, me, is_self=True, hostname=socket.gethostname())
                found += 1
            for mac, ip in read_neighbour_table():
                if ipaddress.ip_address(ip) in net and ip != str(net.broadcast_address):
                    self._record(mac, ip)
                    found += 1
            self.store.expire(time.time() - self.offline_after)
            self.state.update(last_scan=time.time(), last_scan_found=found)
            log.info("sweep of %s done: %d device(s) present", net, found)
            return found
        finally:
            self.state["scanning"] = False

    def _loop(self):
        while not self._stop.is_set():
            try:
                self.sweep()
            except Exception as e:
                self.state["error"] = str(e)
                log.exception("sweep failed")
            self.state["next_scan"] = time.time() + self.interval
            self._wake.wait(self.interval)
            self._wake.clear()

    # -- live engine
    def _live(self):
        if not HAVE_SCAPY:
            self.state["live"] = "unavailable: scapy not installed"
            return
        from scapy.all import ARP, sniff

        def on_packet(pkt):
            if ARP in pkt and pkt[ARP].op in (1, 2):  # who-has and is-at both reveal the sender
                try:
                    net = self.state["subnet"]  # set by the first sweep
                    if net and ipaddress.ip_address(pkt[ARP].psrc) in ipaddress.ip_network(net):
                        self._record(normalize_mac(pkt[ARP].hwsrc), pkt[ARP].psrc)
                except Exception:
                    log.debug("ignored packet", exc_info=True)

        self.state["live"] = "on"
        try:
            sniff(filter="arp", prn=on_packet, store=False, stop_filter=lambda _: self._stop.is_set())
        except Exception as e:
            self.state["live"] = f"unavailable: {e}"
            log.warning("live sniffing unavailable (%s); sweeps still run. "
                        "Run as Administrator/root (and install Npcap on Windows) for instant alerts.", e)
