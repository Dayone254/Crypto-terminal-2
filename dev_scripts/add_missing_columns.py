import sqlite3
from pathlib import Path

db_files = list(Path(".").rglob("*.db"))
print(f"Found {len(db_files)} SQLite databases: {db_files}")

for db in db_files:
    print(f"\nMigrating {db}...")
    try:
        conn = sqlite3.connect(str(db))
        cursor = conn.cursor()
        
        tables = [t[0] for t in cursor.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        
        if "scores" in tables:
            cols = [c[1] for c in cursor.execute("PRAGMA table_info(scores)").fetchall()]
            if "trade_direction" not in cols:
                print(f"  Adding trade_direction column to 'scores' table in {db}")
                cursor.execute("ALTER TABLE scores ADD COLUMN trade_direction TEXT DEFAULT 'LONG'")
        
        if "ladders" in tables:
            cols = [c[1] for c in cursor.execute("PRAGMA table_info(ladders)").fetchall()]
            if "trade_direction" not in cols:
                print(f"  Adding trade_direction column to 'ladders' table in {db}")
                cursor.execute("ALTER TABLE ladders ADD COLUMN trade_direction TEXT DEFAULT 'LONG'")

        if "signals" in tables:
            cols = [c[1] for c in cursor.execute("PRAGMA table_info(signals)").fetchall()]
            if "trade_direction" not in cols:
                print(f"  Adding trade_direction column to 'signals' table in {db}")
                cursor.execute("ALTER TABLE signals ADD COLUMN trade_direction TEXT DEFAULT 'LONG'")

        conn.commit()
        conn.close()
        print(f"  Done migrating {db}")
    except Exception as e:
        print(f"  Error migrating {db}: {e}")
