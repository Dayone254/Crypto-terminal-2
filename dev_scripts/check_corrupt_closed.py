import sqlite3
from datetime import UTC, datetime

conn = sqlite3.connect("f:/Crypto terminal 2/backend/tpt/data/backtest.db")
cursor = conn.cursor()

cursor.execute("SELECT id, symbol, timestamp, filled_at, closed_at, status FROM signals")
rows = cursor.fetchall()

corrupt = []
for r in rows:
    sig_id, sym, ts, fill_t, close_t, status = r
    if fill_t and fill_t < ts:
        corrupt.append((sig_id, sym, "filled_at < timestamp", ts, fill_t, close_t, status))
    elif close_t and close_t < ts:
        corrupt.append((sig_id, sym, "closed_at < timestamp", ts, fill_t, close_t, status))

with open("corrupt_out.txt", "w") as f:
    f.write(f"Total signals: {len(rows)}\n")
    f.write(f"Found {len(corrupt)} signals with back-dated timestamps:\n\n")
    for c in corrupt:
        sig_id, sym, reason, ts, fill_t, close_t, status = c
        dt = datetime.fromtimestamp(ts, tz=UTC).strftime("%Y-%m-%d %H:%M")
        f_dt = datetime.fromtimestamp(fill_t, tz=UTC).strftime("%Y-%m-%d %H:%M") if fill_t else "None"
        c_dt = datetime.fromtimestamp(close_t, tz=UTC).strftime("%Y-%m-%d %H:%M") if close_t else "None"
        f.write(f"ID {sig_id:<3} | {sym:<10} | Reason: {reason:<22} | Created: {dt} | Fill: {f_dt} | Closed: {c_dt} | Status: {status}\n")

print(f"Saved corrupt_out.txt with {len(corrupt)} corrupt signals.")
conn.close()
