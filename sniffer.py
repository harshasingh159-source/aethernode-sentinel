"""AetherNode sensor: watches ARP traffic and records every device on the LAN.

Usage (needs admin/root, and Npcap on Windows):
    python sniffer.py                 # passive: listen for ARP traffic
    python sniffer.py --scan          # also actively ARP-sweep the subnet every 60s
    python sniffer.py --scan --interval 30 --iface "Wi-Fi"
"""
import argparse
import ipaddress
import threading
import time

from scapy.all import ARP, Ether, conf, get_if_addr, sniff, srp

import database


def lookup_vendor(mac):
    # Phones/laptops with "private Wi-Fi address" set the locally-administered bit.
    if int(mac.split(":")[0], 16) & 0x02:
        return "Randomized MAC (private)"
    try:
        result = conf.manufdb.lookup(mac)
        return result[1] or result[0] if result and result[0] != mac else None
    except Exception:
        return None


def record(mac, ip):
    if not mac or mac == "00:00:00:00:00:00" or not ip or ip == "0.0.0.0":
        return
    is_new = database.upsert_device(mac, ip, lookup_vendor(mac))
    name = database.get_hostname(mac)
    if is_new:
        print(f"[!] NEW DEVICE: {ip:<15} {mac}  ({lookup_vendor(mac) or 'unknown vendor'})")
    elif name:
        print(f"[*] friendly: {name} at {ip}")
    else:
        print(f"[?] unverified device: {ip:<15} {mac}")


def process_packet(packet):
    # Both who-has (op=1) and is-at (op=2) reveal the sender's MAC/IP pair.
    if packet.haslayer(ARP) and packet[ARP].op in (1, 2):
        record(packet[ARP].hwsrc, packet[ARP].psrc)


def local_subnet(iface):
    ip = get_if_addr(iface or conf.iface)
    if ip == "0.0.0.0":
        raise RuntimeError("Could not determine local IP; pass --iface")
    return str(ipaddress.ip_network(f"{ip}/24", strict=False))


def scan_loop(iface, interval):
    subnet = local_subnet(iface)
    print(f"[*] Active scanning {subnet} every {interval}s")
    while True:
        try:
            answered, _ = srp(
                Ether(dst="ff:ff:ff:ff:ff:ff") / ARP(pdst=subnet),
                timeout=3, verbose=False, iface=iface,
            )
            for _, reply in answered:
                record(reply[ARP].hwsrc, reply[ARP].psrc)
        except Exception as e:
            print(f"[!] Scan failed: {e}")
        time.sleep(interval)


def main():
    parser = argparse.ArgumentParser(description="AetherNode ARP sensor")
    parser.add_argument("--iface", help="network interface to use (default: scapy's default)")
    parser.add_argument("--scan", action="store_true", help="actively ARP-sweep the /24 subnet")
    parser.add_argument("--interval", type=int, default=60, help="seconds between scans")
    args = parser.parse_args()

    database.init_db()
    print("--- AETHER_NODE_SNIFFER V1.4 ---")
    print(f"[*] Database: {database.DB_PATH}")
    print("[*] Monitoring network for ARP traffic... (Ctrl+C to exit)")

    if args.scan:
        threading.Thread(target=scan_loop, args=(args.iface, args.interval), daemon=True).start()

    try:
        sniff(prn=process_packet, filter="arp", store=0, iface=args.iface)
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"\n[!] Error: {e}")
        print("[?] Hint: run as Administrator/root, and on Windows install Npcap (https://npcap.com).")


if __name__ == "__main__":
    main()
