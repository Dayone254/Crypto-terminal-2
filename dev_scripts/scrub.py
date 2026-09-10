import os
import sqlite3

db_path = os.path.join('F:/Crypto terminal 2/backend', 'backtest.db')
conn = sqlite3.connect(db_path)
cur = conn.cursor()
cur.execute("DELETE FROM signals WHERE symbol IN ('PAXG-USD', 'TEST-USD')")
conn.commit()
print(f'Deleted {cur.rowcount} legacy test signals from backtest.db')
conn.close()
