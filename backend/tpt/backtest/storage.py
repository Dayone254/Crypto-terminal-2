"""Storage module for historical candles and walk-forward backtest results."""
from __future__ import annotations

import logging
import sqlite3
import time
from typing import Any

from tpt.config.settings import settings
from tpt.db.write_lock import db_write_lock

logger = logging.getLogger(__name__)

CREATE_HISTORICAL_CANDLES_SQL = """
CREATE TABLE IF NOT EXISTS historical_candles (
    id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    granularity INTEGER NOT NULL,
    timestamp INTEGER NOT NULL,
    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    close REAL NOT NULL,
    volume REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_hist_candles_sym_tf_ts 
ON historical_candles(symbol, granularity, timestamp);
"""

CREATE_LISTING_BOUNDS_SQL = """
CREATE TABLE IF NOT EXISTS symbol_listing_bounds (
    product_id TEXT PRIMARY KEY,
    first_candle_ts INTEGER NOT NULL,
    last_candle_ts INTEGER NOT NULL,
    total_candles INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
);
"""

SURVIVORSHIP_BIAS_NOTE = "universe = currently-listed symbols, survivorship bias not corrected"


def ensure_backtest_tables() -> None:
    """Ensure historical candles and bounds tables exist in SQLite."""
    db_path = settings.sqlite_path
    with sqlite3.connect(db_path) as conn:
        conn.executescript(CREATE_HISTORICAL_CANDLES_SQL)
        conn.executescript(CREATE_LISTING_BOUNDS_SQL)
        conn.commit()


def save_historical_candles_sync(
    symbol: str,
    granularity: int,
    candles: list[list[Any]],
) -> int:
    """Synchronously insert or replace a batch of OHLCV candles into SQLite.
    
    Candle format: [timestamp, low, high, open, close, volume] or [timestamp, open, high, low, close, volume]
    Normalizes to (id, symbol, granularity, timestamp, open, high, low, close, volume).
    """
    if not candles:
        return 0

    ensure_backtest_tables()
    rows = []
    min_ts = 2**63 - 1
    max_ts = 0

    for c in candles:
        if len(c) < 6:
            continue
        ts = int(c[0])
        # Coinbase candle format: [timestamp, low, high, open, close, volume]
        # or standard: [timestamp, open, high, low, close, volume]
        # Check standard ordering vs Coinbase format
        if float(c[1]) <= float(c[2]) and float(c[3]) <= float(c[2]):
            # low, high, open, close
            low_v, high_v, open_v, close_v = float(c[1]), float(c[2]), float(c[3]), float(c[4])
        else:
            open_v, high_v, low_v, close_v = float(c[1]), float(c[2]), float(c[3]), float(c[4])
        vol_v = float(c[5])

        cid = f"{symbol}_{granularity}_{ts}"
        rows.append((cid, symbol, granularity, ts, open_v, high_v, low_v, close_v, vol_v))
        if ts < min_ts:
            min_ts = ts
        if ts > max_ts:
            max_ts = ts

    if not rows:
        return 0

    db_path = settings.sqlite_path
    with sqlite3.connect(db_path) as conn:
        conn.executemany(
            """INSERT OR REPLACE INTO historical_candles 
            (id, symbol, granularity, timestamp, open, high, low, close, volume)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            rows,
        )
        
        # Update symbol listing bounds
        if min_ts < 2**63 - 1 and max_ts > 0:
            now_iso = conn.execute("SELECT datetime('now')").fetchone()[0]
            conn.execute(
                """INSERT INTO symbol_listing_bounds (product_id, first_candle_ts, last_candle_ts, total_candles, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(product_id) DO UPDATE SET
                    first_candle_ts = MIN(first_candle_ts, excluded.first_candle_ts),
                    last_candle_ts = MAX(last_candle_ts, excluded.last_candle_ts),
                    total_candles = total_candles + excluded.total_candles,
                    updated_at = excluded.updated_at""",
                (symbol, min_ts, max_ts, len(rows), str(now_iso)),
            )

        conn.commit()

    return len(rows)


def load_historical_candles_sync(
    symbol: str,
    granularity: int = 900,
    start_ts: int | None = None,
    end_ts: int | None = None,
    limit: int | None = None,
) -> list[list[Any]]:
    """Load historical candles sorted by timestamp ascending.
    
    Returns list of [timestamp, open, high, low, close, volume].
    """
    ensure_backtest_tables()
    db_path = settings.sqlite_path

    clauses = ["symbol = ?", "granularity = ?"]
    params: list[Any] = [symbol, granularity]

    if start_ts is not None:
        clauses.append("timestamp >= ?")
        params.append(start_ts)
    if end_ts is not None:
        clauses.append("timestamp <= ?")
        params.append(end_ts)

    where = " WHERE " + " AND ".join(clauses)

    if limit is not None:
        sql = f"""SELECT timestamp, open, high, low, close, volume 
                FROM historical_candles {where} 
                ORDER BY timestamp DESC LIMIT {limit}"""
    else:
        sql = f"""SELECT timestamp, open, high, low, close, volume 
                FROM historical_candles {where} 
                ORDER BY timestamp ASC"""

    with sqlite3.connect(db_path, timeout=10.0) as conn:

        cursor = conn.cursor()
        cursor.execute(sql, params)
        rows = cursor.fetchall()

        if limit is not None:
            rows.reverse()

        return [[r[0], r[1], r[2], r[3], r[4], r[5]] for r in rows]




def get_symbol_listing_bounds_sync() -> dict[str, dict[str, Any]]:
    """Get per-symbol listing-date bounds."""
    ensure_backtest_tables()
    db_path = settings.sqlite_path
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT product_id, first_candle_ts, last_candle_ts, total_candles FROM symbol_listing_bounds")
        rows = cursor.fetchall()
        return {
            r[0]: {
                "first_candle_ts": r[1],
                "last_candle_ts": r[2],
                "total_candles": r[3],
            }
            for r in rows
        }
