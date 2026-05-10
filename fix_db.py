import sqlite3

def upgrade_db():
    conn = sqlite3.connect('aethernode.db')
    c = conn.cursor()
    try:
        # This adds the missing 'hostname' column to your existing table
        c.execute("ALTER TABLE devices ADD COLUMN hostname TEXT")
        conn.commit()
        print("[+] Successfully added 'hostname' column!")
    except sqlite3.OperationalError:
        print("[!] Column already exists or database error.")
    finally:
        conn.close()

if __name__ == "__main__":
    upgrade_db()