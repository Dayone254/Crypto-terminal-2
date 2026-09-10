import os
import sqlite3

db_path = os.path.join(os.path.dirname(__file__), 'tpt', 'data', 'backtest.db')
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

# ORDER BY started_at DESC instead of id DESC!
cur.execute("SELECT id, status, started_at, duration_seconds, candidates_count, error_message FROM scan_runs ORDER BY started_at DESC LIMIT 5")
rows = cur.fetchall()

print("--- ACTUAL RECENT RUNS ---")
for r in rows:
    print(f"[{r['started_at']}] {r['status']} | CANDS: {r['candidates_count']} | DUR: {r['duration_seconds']}s")
    
conn.close()
