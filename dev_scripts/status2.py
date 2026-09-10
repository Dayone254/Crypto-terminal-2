import json
import sqlite3

with sqlite3.connect('tpt/data/backtest.db') as c:
    c.row_factory = sqlite3.Row
    rs = c.execute("SELECT id, status, started_at, completed_at, candidates_count, error_message FROM scan_runs ORDER BY started_at DESC LIMIT 1").fetchone()
    print(json.dumps(dict(rs), indent=2))
