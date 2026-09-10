import sqlite3

# 1. Update signals where entry_price was offset from market price
conn = sqlite3.connect("f:/Crypto terminal 2/backend/tpt/data/backtest.db")
cursor = conn.cursor()

# Check how many signals exist
cursor.execute("SELECT id, symbol, trade_direction, entry_price, tp_price, sl_price, timestamp FROM signals")
rows = cursor.fetchall()

print(f"Loaded {len(rows)} signals to test market-fill evaluation:")
for r in rows:
    sig_id, sym, direction, entry, tp, sl, ts = r
    # If entry price was far below market or needed market fill:
    # Recalculate 2.0R TP & SL around entry
    risk = entry * 0.03 # 3% risk
    if direction == "SHORT":
        sl_new = round(entry * 1.03, 6)
        tp_new = round(entry - (2.0 * risk), 6)
    else:
        sl_new = round(entry * 0.97, 6)
        tp_new = round(entry + (2.0 * risk), 6)
    
    # Set fill_price = entry, filled_at = timestamp (Immediate Fill at Entry Zone)
    conn.execute(
        "UPDATE signals SET fill_price = ?, filled_at = ?, tp_price = ?, sl_price = ?, status = 'PENDING', closed_at = NULL, mfe = 0.0, mae = 0.0 WHERE id = ?",
        (entry, ts, tp_new, sl_new, sig_id)
    )

conn.commit()
conn.close()
print("Set immediate fill on all signals. Now running forward evaluator...")
