import json
import os
import sqlite3

for db_path in ["f:/Crypto terminal 2/backend/tpt.db", "f:/Crypto terminal 2/backend/tpt/data/backtest.db"]:
    if os.path.exists(db_path):
        print(f"=== {db_path} ===")
        try:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM signals ORDER BY id DESC LIMIT 10").fetchall()
            print(json.dumps([dict(r) for r in rows], indent=2))
        except Exception as e:
            print("Error:", e)
