import os
import sqlite3

db_path = os.path.join(os.path.dirname(__file__), 'tpt', 'data', 'backtest.db')
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cur = conn.cursor()
cur.execute("SELECT error_message FROM scan_runs WHERE status='FAILED' AND error_message LIKE '%threads can only be started once%' ORDER BY id DESC LIMIT 1")
row = cur.fetchone()
if row:
    print(row['error_message'])
