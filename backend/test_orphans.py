import sqlite3

def check_orphans():
    conn = sqlite3.connect('signals.db')
    cur = conn.cursor()
    # Unique statuses
    cur.execute("SELECT DISTINCT status FROM signals")
    print(f"All unique statuses in ledger: {[r[0] for r in cur.fetchall()]}")
    
    # Check for orphaned trades
    cur.execute("SELECT id, symbol, status FROM signals WHERE status NOT IN ('WIN', 'LOSS', 'EXPIRED', 'PENDING', 'L2_REJECTED', 'BREAK_EVEN', 'PARTIAL_WIN', 'ACTIVE_T2')")
    orphaned = cur.fetchall()
    
    print(f"\nStranded non-terminal trades found: {len(orphaned)}")
    for row in orphaned:
        print(f" ID: {row[0]}, Symbol: {row[1]}, Status: {row[2]}")
        
    cur.execute("SELECT id, symbol, status FROM signals WHERE status = 'ACTIVE_T2'")
    t2s = cur.fetchall()
    print(f"\nACTIVE_T2 trades waiting to be picked up by the fixed query: {len(t2s)}")

if __name__ == '__main__':
    check_orphans()
