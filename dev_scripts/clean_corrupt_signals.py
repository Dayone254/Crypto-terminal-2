import os
import sqlite3


def sanitize_ladder_dict(lad_dict):
    if not lad_dict or not lad_dict.get("tranche_a_price"):
        return lad_dict
    try:
        tranche_a = float(lad_dict["tranche_a_price"])
        stop = float(lad_dict.get("stop_price") or 0.0)
        t1 = float(lad_dict.get("target_1_price") or 0.0)
        t2 = float(lad_dict.get("target_2_price") or 0.0)

        if tranche_a <= 0 or stop <= 0:
            return lad_dict

        is_short = stop > tranche_a

        if is_short:
            risk = stop - tranche_a
            if risk > tranche_a * 0.035:
                risk = tranche_a * 0.03
                stop = tranche_a + risk
                lad_dict["stop_price"] = round(stop, 6)

            min_t1 = tranche_a - (2.0 * risk)
            if t1 > min_t1 or t1 <= 0:
                lad_dict["target_1_price"] = round(min_t1, 6)
                t1 = min_t1

            min_t2 = tranche_a - (4.0 * risk)
            if t2 > t1 or t2 <= 0:
                lad_dict["target_2_price"] = round(min_t2, 6)
                t2 = min_t2

            lad_dict["rr_a_t1"] = round(abs(tranche_a - t1) / risk, 2) if risk > 0 else 2.0
            lad_dict["rr_a_t2"] = round(abs(tranche_a - t2) / risk, 2) if risk > 0 else 4.0
        else:
            risk = tranche_a - stop
            if risk > tranche_a * 0.035:
                risk = tranche_a * 0.03
                stop = tranche_a - risk
                lad_dict["stop_price"] = round(stop, 6)

            min_t1 = tranche_a + (2.0 * risk)
            if t1 < min_t1 or t1 <= 0:
                lad_dict["target_1_price"] = round(min_t1, 6)
                t1 = min_t1

            min_t2 = tranche_a + (4.0 * risk)
            if t2 < t1 or t2 <= 0:
                lad_dict["target_2_price"] = round(min_t2, 6)
                t2 = min_t2

            lad_dict["rr_a_t1"] = round(abs(t1 - tranche_a) / risk, 2) if risk > 0 else 2.0
            lad_dict["rr_a_t2"] = round(abs(t2 - tranche_a) / risk, 2) if risk > 0 else 4.0
    except Exception:
        pass
    return lad_dict

db_path = "f:/Crypto terminal 2/backend/tpt/data/backtest.db"
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    
    # 1. Run schema migration in case init_db hasn't run yet
    try:
        conn.execute("ALTER TABLE signals ADD COLUMN trade_direction TEXT DEFAULT 'LONG'")
    except Exception:
        pass

    # 2. Populate trade_direction for existing signals
    conn.execute("UPDATE signals SET trade_direction='SHORT' WHERE sl_price > entry_price AND (trade_direction IS NULL OR trade_direction='LONG')")
    conn.execute("UPDATE signals SET trade_direction='LONG' WHERE sl_price <= entry_price AND (trade_direction IS NULL OR trade_direction='')")

    # 3. Reset all signals where closed_at < timestamp OR filled_at < timestamp back to PENDING
    res = conn.execute("""
        UPDATE signals 
        SET status = 'PENDING', fill_price = NULL, filled_at = NULL, closed_at = NULL, mfe = 0.0, mae = 0.0 
        WHERE (closed_at IS NOT NULL AND closed_at < timestamp) 
           OR (filled_at IS NOT NULL AND filled_at < timestamp)
    """)
    print(f"Reset {res.rowcount} corrupt back-dated signals back to PENDING status.")

    # 4. Delete duplicate PENDING signals for the same symbol (keep only latest)
    cursor = conn.execute("SELECT symbol, COUNT(*), MAX(id) FROM signals WHERE status='PENDING' GROUP BY symbol HAVING COUNT(*) > 1")
    dupes = cursor.fetchall()
    deleted_dupes = 0
    for sym, count, max_id in dupes:
        res = conn.execute("DELETE FROM signals WHERE symbol=? AND status='PENDING' AND id != ?", (sym, max_id))
        deleted_dupes += res.rowcount
    print(f"Deleted {deleted_dupes} duplicate PENDING signals.")

    # 5. Sanitize all signals to strictly enforce minimum 2.0R to 4.0R R:R
    cursor = conn.execute("SELECT id, symbol, trade_direction, entry_price, tp_price, sl_price FROM signals")
    rows = cursor.fetchall()
    sanitized_count = 0
    for r in rows:
        sig_id, sym, direction, entry, tp, sl = r
        if entry and tp and sl:
            lad_dict = {
                "tranche_a_price": entry,
                "stop_price": sl,
                "target_1_price": tp,
                "target_2_price": 0.0
            }
            sanitized = sanitize_ladder_dict(lad_dict)
            if sanitized:
                new_tp = sanitized["target_1_price"]
                new_sl = sanitized["stop_price"]
                if abs(new_tp - tp) > 1e-6 or abs(new_sl - sl) > 1e-6:
                    conn.execute("UPDATE signals SET tp_price = ?, sl_price = ? WHERE id = ?", (new_tp, new_sl, sig_id))
                    sanitized_count += 1

    print(f"Sanitized {sanitized_count} signals to strictly enforce 2.0R+ Risk-to-Reward ratio.")

    conn.commit()
    conn.close()
    print("Database scrub complete.")
else:
    print("Database file not found.")
