import sqlite3, statistics, sys

DB = "tpt/data/backtest.db"

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

with open("diag_output.txt", "w") as f:
    try:
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [r[0] for r in cur.fetchall()]
        f.write(f"TABLES: {tables}\n")
        
        # 3. All resolved trades — win rate by label
        cur.execute("""
            SELECT label, status, score, mae, mfe
            FROM signals
            WHERE status IN ('WIN','LOSS', 'PARTIAL_WIN', 'BREAK_EVEN')
        """)
        rows = cur.fetchall()
        f.write(f"\n=== CLOSED TRADES ({len(rows)} total) ===\n")
        by_label = {}
        for r in rows:
            lbl = r['label'] or 'UNKNOWN'
            if lbl not in by_label:
                by_label[lbl] = {'WIN':0,'LOSS':0, 'OTHER': 0,'mae':[],'mfe':[],'scores':[]}
            d = by_label[lbl]
            if r['status'] == 'WIN':
                d['WIN'] += 1
            elif r['status'] == 'LOSS':
                d['LOSS'] += 1
            else:
                d['OTHER'] += 1
                
            if r['mae'] is not None: d['mae'].append(float(r['mae']))
            if r['mfe'] is not None: d['mfe'].append(float(r['mfe']))
            if r['score'] is not None: d['scores'].append(float(r['score']))

        for lbl, d in sorted(by_label.items()):
            total = d['WIN'] + d['LOSS']
            wr = d['WIN']/total*100 if total else 0
            avg_mae = statistics.mean(d['mae']) if d['mae'] else 0
            avg_mfe = statistics.mean(d['mfe']) if d['mfe'] else 0
            avg_score = statistics.mean(d['scores']) if d['scores'] else 0
            f.write(f"  {lbl:15s}: {d['WIN']:3d}W / {d['LOSS']:3d}L / {d['OTHER']:3d}O  WR={wr:5.1f}%  AvgScore={avg_score:5.1f}  AvgMAE={avg_mae:+.2f}%  AvgMFE={avg_mfe:+.2f}%\n")

        cur.execute("SELECT COUNT(*) as n FROM signals WHERE status='PENDING'")
        f.write(f"\n=== PENDING TRADES: {cur.fetchone()['n']} ===\n")

        # MAE distribution of LOSSES
        cur.execute("SELECT mae FROM signals WHERE status='LOSS' AND mae IS NOT NULL")
        losses_mae = [float(r['mae']) for r in cur.fetchall()]
        if losses_mae:
            f.write(f"LOSS MAE Dist: avg={statistics.mean(losses_mae):+.2f}%  min={min(losses_mae):+.2f}%  max={max(losses_mae):+.2f}%\n")
            
    except Exception as e:
        f.write(f"Error querying DB: {e}\n")
    finally:
        conn.close()
