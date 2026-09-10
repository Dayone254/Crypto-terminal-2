import sqlite3

c = sqlite3.connect('tpt/data/backtest.db')
c.row_factory = sqlite3.Row

scan = c.execute("SELECT * FROM scan_runs ORDER BY started_at DESC LIMIT 1").fetchone()
if not scan:
    print("NO SCANS.")
    exit(0)

print("LATEST SCAN:")
print(f"ID: {scan['id']}")
print(f"Status: {scan['status']}")
print("ERROR MESSAGE:")
print(scan['error_message'])
