"""Shadow signal persistence — time-dedup regression tests.

History: persist_shadow_signals had NO dedup, so every scan re-recorded every
still-actionable setup across all staged cohorts (five shadow pipelines) —
1,630 shadow rows vs 228 live rows in a 6h window. The flood buried the live
ledger's fresh-200 page and rotated the visible trades on every refresh.
"""
import time

import aiosqlite
import pytest

from tpt.backtest.shadow_engine import persist_shadow_signals

_SCHEMA = """
CREATE TABLE signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_run_id TEXT,
    symbol TEXT NOT NULL,
    timestamp INTEGER NOT NULL,
    score REAL NOT NULL DEFAULT 0,
    score_breakdown TEXT,
    label TEXT NOT NULL DEFAULT 'ENTRY_ZONE',
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
    pipeline_version TEXT DEFAULT 'v2.0',
    position_size_usd REAL
)
"""


def _rec(symbol: str, pv: str, **kw) -> dict:
    base = {
        "scan_run_id": "run-1",
        "symbol": symbol,
        "score": 70.0,
        "score_breakdown": "{}",
        "label": "ENTRY_ZONE",
        "trade_direction": "LONG",
        "entry_price": 100.0,
        "tp_price": 110.0,
        "tp2_price": 120.0,
        "sl_price": 95.0,
        "position_size_usd": 100.0,
        "status": "PENDING",
        "pipeline_version": pv,
    }
    base.update(kw)
    return base


class _FakeConnCtx:
    """Mimics get_connection(): async CM yielding the same aiosqlite conn."""

    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, *a):
        return False


async def _make_db():
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    await conn.execute(_SCHEMA)
    await conn.commit()
    return conn


class _FakeWriteLock:
    """Async CM standing in for db_write_lock (no cross-test contention)."""

    async def __aenter__(self):
        return None

    async def __aexit__(self, *a):
        return False


def _patch_infra(monkeypatch, db):
    """Point persist_shadow_signals at the temp DB.

    Both dependencies are imported INSIDE the function body, so they must be
    patched at their source modules — patching tpt.backtest.shadow_engine's
    own attributes would be silently ignored and the test would touch the
    live database.
    """
    import tpt.data.database as db_mod
    import tpt.db.write_lock as wl_mod
    monkeypatch.setattr(db_mod, "get_connection", lambda: _FakeConnCtx(db))
    monkeypatch.setattr(wl_mod, "db_write_lock", _FakeWriteLock())


@pytest.mark.asyncio
async def test_repeated_setup_within_window_is_not_reinserted(monkeypatch):
    db = await _make_db()
    _patch_infra(monkeypatch, db)

    rec = _rec("CRV-USD", "v3.1-gamma-pin-reversion")
    n1 = await persist_shadow_signals([rec])
    assert n1 == 1

    # Same cohort, same symbol, minutes later (next scan): suppressed.
    n2 = await persist_shadow_signals([dict(rec, scan_run_id="run-2")])
    assert n2 == 0

    # A DIFFERENT cohort still records its own copy (parallel history is the point).
    n3 = await persist_shadow_signals([_rec("CRV-USD", "v3.0-staged")])
    assert n3 == 1

    # A DIFFERENT symbol under the first cohort still records.
    n4 = await persist_shadow_signals([_rec("LTC-USD", "v3.1-gamma-pin-reversion")])
    assert n4 == 1

    rows = (await (await db.execute("SELECT COUNT(*) FROM signals")).fetchone())[0]
    assert rows == 3


@pytest.mark.asyncio
async def test_window_expiry_allows_a_fresh_shadow_row(monkeypatch):
    db = await _make_db()
    _patch_infra(monkeypatch, db)

    # An open row from 5 hours ago no longer blocks: the dedup window is 4h,
    # matching the live path's rule.
    old_ts = int(time.time()) - 5 * 3600
    await db.execute(
        """INSERT INTO signals (symbol, timestamp, entry_price, tp_price, sl_price, status, pipeline_version)
        VALUES ('CRV-USD', ?, 100.0, 110.0, 95.0, 'PENDING', 'v3.1-gamma-pin-reversion')""",
        (old_ts,),
    )
    await db.commit()

    n = await persist_shadow_signals([_rec("CRV-USD", "v3.1-gamma-pin-reversion")])
    assert n == 1


@pytest.mark.asyncio
async def test_in_trade_and_active_t2_still_block_reinsertion(monkeypatch):
    db = await _make_db()
    _patch_infra(monkeypatch, db)

    now = int(time.time())
    for status in ("IN_TRADE", "ACTIVE_T2"):
        await db.execute(
            """INSERT INTO signals (symbol, timestamp, entry_price, tp_price, sl_price, status, pipeline_version)
            VALUES ('CRV-USD', ?, 100.0, 110.0, 95.0, ?, 'v3.1-gamma-pin-reversion')""",
            (now - 60, status),
        )
    await db.commit()

    n = await persist_shadow_signals([_rec("CRV-USD", "v3.1-gamma-pin-reversion")])
    assert n == 0


@pytest.mark.asyncio
async def test_closed_shadow_row_does_not_block_a_new_signal(monkeypatch):
    db = await _make_db()
    _patch_infra(monkeypatch, db)

    now = int(time.time())
    await db.execute(
        """INSERT INTO signals (symbol, timestamp, entry_price, tp_price, sl_price, status, closed_at, pipeline_version)
        VALUES ('CRV-USD', ?, 100.0, 110.0, 95.0, 'WIN', ?, 'v3.1-gamma-pin-reversion')""",
        (now - 600, now - 30),
    )
    await db.commit()

    n = await persist_shadow_signals([_rec("CRV-USD", "v3.1-gamma-pin-reversion")])
    assert n == 1
