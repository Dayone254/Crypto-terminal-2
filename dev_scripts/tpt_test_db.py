import sqlite3


def test_insert():
    db_path = "f:/Crypto terminal 2/backend/tpt/data/backtest.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute('''
        INSERT INTO signals 
        (scan_run_id, symbol, timestamp, score, score_breakdown, label, trade_direction, entry_price, tp_price, tp2_price, sl_price) 
        VALUES (?, ?, strftime('%s', 'now'), ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (1, 'TEST-USD', 99.0, '{"x": 1}', 'ENTRY_ZONE', 'LONG', 10.0, 12.0, 14.0, 9.0))
        conn.commit()
        print("Success inserting into backtest.db")
    except Exception as e:
        print("Failed to insert into backtest.db:", e)
        
if __name__ == "__main__":
    test_insert()
