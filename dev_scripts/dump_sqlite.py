import json
import os
import sqlite3

db_path = os.path.join(os.path.dirname(__file__), 'tpt', 'data', 'backtest.db')
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

cur.execute("SELECT id, status, candidates_count, error_message FROM scan_runs ORDER BY id DESC LIMIT 5")
rows = cur.fetchall()

out = []
for r in rows:
    out.append({"id": r['id'], "status": r['status'], "cands": r['candidates_count'], "error": r['error_message']})

with open("db_out.json", "w") as f:
    json.dump(out, f, indent=2)
conn.close()
