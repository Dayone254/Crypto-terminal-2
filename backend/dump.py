import sqlite3
import sys

db_path = "tpt/data/backtest.db"

def run():
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute('''
            SELECT id as signal_id, symbol as product_id, status, pipeline_version, 
                   mfe, mae, 
                   tp_price, sl_price, entry_price, filled_at, closed_at, label
            FROM signals 
            WHERE status IN ('WIN', 'LOSS', 'PARTIAL_WIN', 'BREAK_EVEN')
            ORDER BY id DESC LIMIT 8
        ''')
        rows = c.fetchall()
        for i, r in enumerate(rows):
            d = dict(r)
            print(f"[{i+1}] {d['product_id']} ({d['label']}) | Status: {d['status']} | Pipeline: {d['pipeline_version']} | MFE: {d['mfe']} | MAE: {d['mae']}")
            print(f"      Entry: {d['entry_price']} | Target: {d['tp_price']} | SL: {d['sl_price']}")
    except Exception as e:
        print("Error in backtest.db trades:", e)

if __name__ == "__main__":
    run()
