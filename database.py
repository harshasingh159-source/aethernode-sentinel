import sqlite3

def init_db():
    # This creates a file called 'aethernode.db'
    conn = sqlite3.connect('aethernode.db')
    c = conn.cursor()
    
    # Create a table to store our 'Known' devices
    c.execute('''CREATE TABLE IF NOT EXISTS devices
                 (mac TEXT PRIMARY KEY, 
                  ip TEXT, 
                  last_seen TEXT, 
                  status TEXT DEFAULT 'Unknown')''')
    
    conn.commit()
    conn.close()
    print("[+] Database Ready: aethernode.db created.")

if __name__ == "__main__":
    init_db()