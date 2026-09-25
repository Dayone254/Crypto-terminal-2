import logging
import os
from typing import Any

import duckdb

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "tpt_timeseries.duckdb")

class DuckDBStore:
    """
    Embedded high-performance time-series database engine using DuckDB.
    Handles high-frequency tick logging, L2 snapshot archives, and fast 
    multi-timeframe candle aggregations with zero SQLite lock contention.
    """

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._conn: duckdb.DuckDBPyConnection | None = None
        self._init_db()

    def _get_connection(self) -> duckdb.DuckDBPyConnection:
        if self._conn is None:
            self._conn = duckdb.connect(self.db_path)
        return self._conn

    def _init_db(self):
        """Initializes time-series tables and indexes."""
        conn = self._get_connection()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ticks (
                timestamp TIMESTAMP,
                symbol VARCHAR,
                exchange VARCHAR,
                price DOUBLE,
                volume DOUBLE,
                side VARCHAR
            );
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS l2_snapshots (
                timestamp TIMESTAMP,
                symbol VARCHAR,
                total_bid_vol DOUBLE,
                total_ask_vol DOUBLE,
                imbalance_ratio DOUBLE,
                top_bid_price DOUBLE,
                top_ask_price DOUBLE
            );
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_ticks_symbol_ts ON ticks(symbol, timestamp);
        """)
        logger.info(f"Initialized DuckDB time-series store at {self.db_path}")

    def log_tick(self, symbol: str, exchange: str, price: float, volume: float, side: str, timestamp: float | None = None):
        """Logs a single real-time trade tick into DuckDB."""
        conn = self._get_connection()
        ts_str = f"to_timestamp({timestamp})" if timestamp else "now()"
        conn.execute(
            f"INSERT INTO ticks VALUES ({ts_str}, ?, ?, ?, ?, ?)",
            [symbol, exchange, price, volume, side]
        )

    def log_l2_snapshot(self, symbol: str, bid_vol: float, ask_vol: float, imbalance: float, top_bid: float, top_ask: float):
        """Logs an L2 orderbook snapshot into DuckDB."""
        conn = self._get_connection()
        conn.execute(
            "INSERT INTO l2_snapshots VALUES (now(), ?, ?, ?, ?, ?, ?)",
            [symbol, bid_vol, ask_vol, imbalance, top_bid, top_ask]
        )

    def aggregate_candles(self, symbol: str, timeframe_minutes: int = 5, limit: int = 200) -> list[dict[str, Any]]:
        """
        Executes instant SQL time-bucket candle aggregation over raw tick data.
        Returns OHLCV candles formatted for charting and scanning.
        """
        conn = self._get_connection()
        query = f"""
            SELECT 
                epoch(time_bucket(INTERVAL '{timeframe_minutes} minutes', timestamp)) * 1000 AS timestamp,
                FIRST(price) AS open,
                MAX(price) AS high,
                MIN(price) AS low,
                LAST(price) AS close,
                SUM(volume) AS volume
            FROM ticks
            WHERE symbol = ?
            GROUP BY 1
            ORDER BY timestamp DESC
            LIMIT ?
        """
        result = conn.execute(query, [symbol, limit]).fetchall()
        candles = []
        for r in reversed(result):
            candles.append({
                "timestamp": int(r[0]),
                "open": float(r[1]),
                "high": float(r[2]),
                "low": float(r[3]),
                "close": float(r[4]),
                "volume": float(r[5])
            })
        return candles

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None

duckdb_store = DuckDBStore()
