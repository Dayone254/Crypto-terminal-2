import sqlite3


def check():
    print("Checking scan runs...")
    with sqlite3.connect('tpt/data/backtest.db') as c:
        c.row_factory = sqlite3.Row
        rs = c.execute("SELECT id, status, started_at, completed_at, candidates_count FROM scan_runs ORDER BY started_at DESC LIMIT 3").fetchall()
        for r in rs:
            print("---")
            for k in r.keys():
                print(f"{k}: {r[k]}")

if __name__ == '__main__':
    check()
