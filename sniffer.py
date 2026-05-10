from scapy.all import sniff, ARP
import sqlite3
from datetime import datetime

def save_to_db(mac, ip):
    conn = sqlite3.connect('aethernode.db')
    c = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # We use INSERT OR IGNORE first to ensure the row exists
    c.execute("INSERT OR IGNORE INTO devices (mac, ip, last_seen, status) VALUES (?, ?, ?, 'Unknown')", 
              (mac, ip, now))
    # Then we update the IP and Last Seen time regardless
    c.execute("UPDATE devices SET ip = ?, last_seen = ? WHERE mac = ?", 
              (ip, now, mac))
    
    conn.commit()
    conn.close()

def get_nickname(mac):
    conn = sqlite3.connect('aethernode.db')
    c = conn.cursor()
    # Look for the name you assigned in React
    c.execute("SELECT hostname FROM devices WHERE mac = ?", (mac,))
    result = c.fetchone()
    conn.close()
    return result[0] if result and result[0] else None

def process_packet(packet):
    # op=2 means an ARP Reply (a device saying "I am here!")
    if packet.haslayer(ARP) and packet[ARP].op == 2:
        ip = packet[ARP].psrc
        mac = packet[ARP].hwsrc
        
        # Check if we recognize this device from our React "Identify" step
        nickname = get_nickname(mac)
        
        if nickname:
            print(f"[*] FRIENDLY DEVICE: {nickname} is active at {ip}")
        else:
            print(f"[!] UNKNOWN DEVICE DETECTED: {ip} | {mac}")
        
        # Save/Update in the database
        save_to_db(mac, ip)

print("--- AETHER_NODE_SNIFFER V1.2 ---")
print("[*] Monitoring network for ARP traffic...")
print("[*] (Press Ctrl+C to exit)")

# Start sniffing
try:
    sniff(prn=process_packet, filter="arp", store=0)
except Exception as e:
    print(f"\n[!] Error: {e}")
    print("[?] Hint: Did you remember to 'Run as Administrator'?")