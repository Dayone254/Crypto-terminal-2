import json
import sqlite3

conn = sqlite3.connect('tpt/data/backtest.db')
conn.row_factory = sqlite3.Row
cur = conn.cursor()

sig = cur.execute("SELECT * FROM signals WHERE id=185").fetchone()
if sig:
    d = dict(sig)
    for k, v in d.items():
        print(f"{k}: {v}")
    if d.get('ladder_json'):
        print("\nParsed Ladder:")
        print(json.dumps(json.loads(d['ladder_json']), indent=2))
