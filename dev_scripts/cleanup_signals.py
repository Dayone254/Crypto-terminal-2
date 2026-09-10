import os
import sqlite3
import time

db_path = os.path.join(os.path.dirname(__file__), 'tpt', 'data', 'backtest.db')
conn = sqlite3.connect(db_path)
cur = conn.cursor()

# Remove fake TEST-USD data
cur.execute("DELETE FROM signals WHERE symbol='TEST-USD'")

# Remove stale PENDING signals older than 48 hours
cutoff = int(time.time()) - 48 * 3600
cur.execute("DELETE FROM signals WHERE status='PENDING' AND CAST(timestamp AS INTEGER) < ?", (cutoff,))

print('Rows cleaned:', conn.total_changes)

cur.execute("SELECT COUNT(*) FROM signals")
print('Remaining signals:', cur.fetchone()[0])

cur.execute("SELECT symbol, label, status FROM signals ORDER BY id DESC LIMIT 5")
print('Recent signals:', cur.fetchall())

conn.commit()
conn.close()
