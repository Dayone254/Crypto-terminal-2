import os
import sqlite3

db_path = os.path.join(os.path.dirname(__file__), 'tpt', 'data', 'backtest.db')
print("Checking DB:", db_path)
if not os.path.exists(db_path):
    print("Database not found:", db_path)
else:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT id, status, error_message, duration_seconds, completed_at FROM scan_runs ORDER BY id DESC LIMIT 1")
    row = cur.fetchone()
    if row:
        print("--- LATEST SCAN DUMP ---")
        print(f"RUN ID: {row[0]}")
        print(f"STATUS: {row[1]}")
        print(f"DURATION: {row[3]}s")
        print(f"COMPLETED AT: {row[4]}")
        if row[2]:
            print(f"ERROR:\n{row[2]}")
    else:
        print("No logs found in DB.")
    conn.close()
