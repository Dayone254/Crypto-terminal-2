import sqlite3

conn = sqlite3.connect("f:/Crypto terminal 2/backend/tpt/data/backtest.db")
cursor = conn.cursor()
cursor.execute("SELECT id, symbol, label, trade_direction, entry_price, tp_price, sl_price, status FROM signals")
rows = cursor.fetchall()

print(f"Total signals in DB: {len(rows)}")

bad_rr = []
for r in rows:
    sig_id, symbol, label, direction, entry, tp, sl, status = r
    if entry and tp and sl:
        if direction == "SHORT" or sl > entry:
            risk = abs(sl - entry)
            reward = abs(entry - tp)
        else:
            risk = abs(entry - sl)
            reward = abs(tp - entry)
        
        rr = reward / risk if risk > 0 else 0
        if rr < 1.8:
            bad_rr.append((sig_id, symbol, direction, entry, tp, sl, round(rr, 2), status))

with open("bad_rr.txt", "w") as f:
    f.write(f"Total signals in DB: {len(rows)}\n")
    f.write(f"Found {len(bad_rr)} signals with R:R < 1.8:\n\n")
    for b in bad_rr:
        f.write(f"ID {b[0]:<3} | {b[1]:<10} ({b[2]:<5}) | Entry: {b[3]:<10} | TP: {b[4]:<10} | SL: {b[5]:<10} | R:R: {b[6]}R | Status: {b[7]}\n")

print("Saved bad_rr.txt")
