import os
import sqlite3

db_path = os.path.join(os.path.dirname(__file__), 'tpt', 'data', 'backtest.db')
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

cur.execute("SELECT id, symbol, status, filled_at, fill_price, tp_price, sl_price, entry_price FROM signals WHERE filled_at IS NOT NULL ORDER BY id DESC LIMIT 10")
rows = cur.fetchall()

print("--- FILLED SIGNALS ---")
for r in rows:
    print(f"[{r['id']}] {r['symbol']} | STAT: {r['status']} | FILLED: {r['filled_at']} | F_PRICE: {r['fill_price']}")
    
conn.close()
