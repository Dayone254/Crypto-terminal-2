import asyncio
import logging
import sqlite3
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("clean_false_fills")

DB_PATHS = [
    Path("tpt/data/backtest.db")
]

def reset_database(db_path: Path):
    if not db_path.exists():
        logger.warning("Database path %s does not exist", db_path)
        return

    logger.info("Resetting all filled signals in %s to PENDING...", db_path)
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    # Reset all signals to PENDING for clean re-evaluation
    cursor.execute("""
        UPDATE signals
        SET status = 'PENDING',
            filled_at = NULL,
            fill_price = NULL,
            closed_at = NULL,
            mfe = 0.0,
            mae = 0.0
    """)
    conn.commit()
    count = cursor.rowcount
    conn.close()
    logger.info("Reset %d signals to PENDING in %s", count, db_path)

if __name__ == "__main__":
    for db in DB_PATHS:
        reset_database(db)

    print("\nStarting clean signal re-evaluation with fixed Coinbase fetcher...")
    from tpt.engine.evaluator import process_signals
    asyncio.run(process_signals())
    print("\n🎉 Signal re-evaluation complete!")
