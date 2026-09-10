import sqlite3
from datetime import UTC, datetime

conn = sqlite3.connect("f:/Crypto terminal 2/backend/tpt/data/backtest.db")
cursor = conn.cursor()

cursor.execute("SELECT id, symbol, label, trade_direction, entry_price, fill_price, tp_price, sl_price, timestamp, filled_at, closed_at, status, mfe, mae FROM signals ORDER BY timestamp DESC")
rows = cursor.fetchall()

wins = [r for r in rows if r[11] == 'WIN']
losses = [r for r in rows if r[11] == 'LOSS']
pending = [r for r in rows if r[11] == 'PENDING']

with open("eval_results.txt", "w", encoding="utf-8") as f:
    f.write(f"Total signals evaluated: {len(rows)}\n")
    f.write(f"  ✓ WIN: {len(wins)}\n")
    f.write(f"  ✗ LOSS: {len(losses)}\n")
    f.write(f"  ⏳ PENDING: {len(pending)}\n\n")

    f.write("--- CLOSED TRADES (LEGITIMATELY EVALUATED POST-SIGNAL) ---\n")
    for r in wins + losses:
        sig_id, sym, lbl, direction, entry, fill_p, tp, sl, ts, fill_t, close_t, status, mfe, mae = r
        dt = datetime.fromtimestamp(ts, tz=UTC).strftime("%Y-%m-%d %H:%M")
        f_dt = datetime.fromtimestamp(fill_t, tz=UTC).strftime("%Y-%m-%d %H:%M") if fill_t else "None"
        c_dt = datetime.fromtimestamp(close_t, tz=UTC).strftime("%Y-%m-%d %H:%M") if close_t else "None"
        f.write(f"ID {sig_id:<3} | {sym:<10} ({direction:<5}) | Status: {status:<4} | Created: {dt} | Fill: {f_dt} (at ${fill_p}) | Closed: {c_dt} | MFE: +{mfe:.2f}% | MAE: {mae:.2f}%\n")

print("Saved eval_results.txt")
conn.close()
