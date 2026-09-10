"""Raw (non-ORM) SQLite access for the signals / backtest tables.

The database path is derived from `settings.database_url` so that the ORM layer
and this raw layer can never diverge onto different files.
"""
import contextlib
import os
import sqlite3
from contextlib import asynccontextmanager

import aiosqlite

from tpt.config.settings import settings

DATA_DIR = os.path.dirname(os.path.abspath(__file__))

# Single source of truth: whatever DATABASE_URL points at.
DB_PATH = settings.sqlite_path

# Must match db/connection.py so every writer shares one starvation budget.
BUSY_TIMEOUT_MS = 30_000
CONNECT_TIMEOUT_S = 30.0

_SIGNALS_COLUMNS = [
    ("scan_run_id", "INTEGER REFERENCES scan_runs(id)"),
    ("filled_at", "INTEGER"),
    ("fill_price", "REAL"),
    ("trade_direction", "TEXT DEFAULT 'LONG'"),
    ("score_breakdown", "TEXT"),
    ("tp2_price", "REAL"),
    ("partial_exit_at", "INTEGER"),
    ("partial_exit_price", "REAL"),
    ("final_status", "TEXT"),
    ("trail_sl", "REAL"),
]


async def init_db():
    """Initializes the raw signals database schema if it doesn't exist."""
    async with aiosqlite.connect(DB_PATH, timeout=CONNECT_TIMEOUT_S) as db:
        await db.execute("PRAGMA journal_mode=WAL;")
        await db.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS};")
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scan_run_id INTEGER REFERENCES scan_runs(id),
                symbol TEXT NOT NULL,
                timestamp INTEGER NOT NULL,
                score REAL NOT NULL,
                score_breakdown TEXT,
                label TEXT NOT NULL,
                trade_direction TEXT NOT NULL DEFAULT 'LONG',
                entry_price REAL NOT NULL,
                tp_price REAL NOT NULL,
                tp2_price REAL,
                sl_price REAL NOT NULL,
                status TEXT NOT NULL DEFAULT 'PENDING',
                mfe REAL DEFAULT 0.0,
                mae REAL DEFAULT 0.0,
                closed_at INTEGER,
                filled_at INTEGER,
                fill_price REAL,
                partial_exit_at INTEGER,
                partial_exit_price REAL,
                final_status TEXT,
                trail_sl REAL
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS component_feedback (
                component TEXT PRIMARY KEY,
                hit_rate REAL NOT NULL,
                total_occurrences INTEGER NOT NULL,
                last_computed_at TEXT NOT NULL
            )
            """
        )
        # Migrate existing DBs that lack newer columns.
        for col, definition in _SIGNALS_COLUMNS:
            # Column already exists on an up-to-date database.
            with contextlib.suppress(Exception):
                await db.execute(f"ALTER TABLE signals ADD COLUMN {col} {definition}")
        # Indexes
        await db.execute("CREATE INDEX IF NOT EXISTS idx_signals_status ON signals(status)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_signals_symbol ON signals(symbol)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_signals_scan_run ON signals(scan_run_id)")
        await db.commit()


@asynccontextmanager
async def get_connection():
    """Returns an async connection context manager with WAL & busy timeout configured."""
    async with aiosqlite.connect(DB_PATH, timeout=CONNECT_TIMEOUT_S) as conn:
        await conn.execute("PRAGMA journal_mode=WAL;")
        await conn.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS};")
        conn.row_factory = aiosqlite.Row
        yield conn


def get_sync_connection() -> sqlite3.Connection:
    """Returns a sync connection for fast reads or initialization."""
    conn = sqlite3.connect(DB_PATH, timeout=CONNECT_TIMEOUT_S)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS};")
    conn.row_factory = sqlite3.Row
    return conn
