import sqlite3
from datetime import UTC, datetime

conn = sqlite3.connect("f:/Crypto terminal 2/backend/tpt/data/backtest.db")
cursor = conn.cursor()
cursor.execute("SELECT id, symbol, timestamp, label, trade_direction, entry_price, tp_price, sl_price, fill_price, filled_at, closed_at, status FROM signals WHERE symbol='CHIP-USD'")
rows = cursor.fetchall()

with open("chip_out.txt", "w") as f:
    f.write(f"Found {len(rows)} signals for CHIP-USD:\n")
    for r in rows:
        sig_id, sym, ts, label, direction, entry, tp, sl, fill_p, fill_t, close_t, status = r
        dt = datetime.fromtimestamp(ts, tz=UTC).strftime("%Y-%m-%d %H:%M:%S")
        f_dt = datetime.fromtimestamp(fill_t, tz=UTC).strftime("%Y-%m-%d %H:%M:%S") if fill_t else "None"
        c_dt = datetime.fromtimestamp(close_t, tz=UTC).strftime("%Y-%m-%d %H:%M:%S") if close_t else "None"
        f.write(f"ID {sig_id} | Signal Time: {dt} ({ts})\n")
        f.write(f"  Direction: {direction} | Entry: {entry} | TP: {tp} | SL: {sl}\n")
        f.write(f"  Fill Price: {fill_p} | Fill Time: {f_dt} ({fill_t}) | Closed Time: {c_dt} ({close_t}) | Status: {status}\n")

print("Saved chip_out.txt")

conn.close()
