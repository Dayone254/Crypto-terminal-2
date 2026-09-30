"""Tests for the IN_TRADE lifecycle state.

History: filled trades kept status='PENDING' forever, so the edge page's
'IN TRADE' tab was really 'every waiting order', and /trades' fresh-200 page
(ORDER BY id DESC LIMIT 200) rotated activated trades out of view on every
refresh — they existed in the DB but were invisible, which made it impossible
to track whether the system has an edge.
"""
import time

import aiosqlite
import pytest

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
    partial_exit_at INTEGER,
    partial_exit_price REAL,
    final_status TEXT,
    trail_sl REAL,
    pipeline_version TEXT DEFAULT 'v2.0',
    position_size_usd REAL
)
"""


async def _insert_row(cur, symbol, **kw):
    base = dict(
        symbol=symbol, timestamp=int(time.time()) - 60, score=70.0,
        label="ENTRY_ZONE", trade_direction="LONG", entry_price=100.0,
        tp_price=110.0, tp2_price=120.0, sl_price=95.0, status="PENDING",
        pipeline_version="v2.0",
    )
    base.update(kw)
    cols = ",".join(base)
    qs = ",".join("?" for _ in base)
    await cur.execute(f"INSERT INTO signals ({cols}) VALUES ({qs})", tuple(base.values()))


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
    # _shadow_exclusion() subqueries this table on live-scope queries.
    await conn.execute(
        "CREATE TABLE shadow_pipelines (pipeline_version TEXT PRIMARY KEY)"
    )
    await conn.execute(
        "INSERT INTO shadow_pipelines VALUES ('v3.1-gamma-pin-reversion')"
    )
    await conn.commit()
    return conn


@pytest.mark.asyncio
async def test_fill_promotes_to_in_trade_and_survives_outcome_write(monkeypatch):
    """End-to-end evaluator pass on a temp DB:
    - A: unfilled PENDING that fills this pass  -> IN_TRADE (not PENDING)
    - B: filled PENDING that hits T1 this pass  -> ACTIVE_T2
    - C: filled PENDING that hits SL this pass  -> LOSS (never demoted)
    The promotion must run AFTER the outcome executemany, or A's stale
    'PENDING' from the outcome write would survive (the original bug class).
    """
    import tpt.engine.evaluator as ev

    db = await _make_db()
    cur = await db.cursor()
    await _insert_row(cur, "AAA-USD")  # fills, no TP/SL touch
    await _insert_row(cur, "BBB-USD", filled_at=int(time.time()) - 30, fill_price=100.0)
    await _insert_row(cur, "CCC-USD", filled_at=int(time.time()) - 30, fill_price=100.0)
    await db.commit()

    now = int(time.time())
    candles = {
        # low 99 <= entry 100 -> fill; high 103 < 110 TP; low 99 > 95 SL
        "AAA-USD": [[now - 900, 99.0, 103.0, 100.5, 102.0, 1.0]],
        # high 111 >= eff_tp 110 -> T1 hit -> ACTIVE_T2
        "BBB-USD": [[now - 900, 100.0, 111.0, 101.0, 108.0, 1.0]],
        # low 94 <= eff_sl 95 -> LOSS
        "CCC-USD": [[now - 900, 94.0, 101.0, 100.0, 96.0, 1.0]],
    }

    async def fake_fetch(client, symbol, start_ts):
        return candles[symbol]

    monkeypatch.setattr(ev, "get_connection", lambda: _FakeConnCtx(db))
    monkeypatch.setattr(ev, "_fetch_candles", fake_fetch)

    await ev.process_signals()

    rows = {}
    async with db.execute("SELECT symbol, status, filled_at, closed_at FROM signals") as cur2:
        for r in await cur2.fetchall():
            rows[r["symbol"]] = dict(r)

    assert rows["AAA-USD"]["status"] == "IN_TRADE"
    assert rows["AAA-USD"]["filled_at"] is not None
    assert rows["BBB-USD"]["status"] == "ACTIVE_T2"
    assert rows["CCC-USD"]["status"] == "LOSS"
    await db.close()


@pytest.mark.asyncio
async def test_promotion_guard_never_flips_closed_rows(monkeypatch):
    """The guarded UPDATE must only flip rows that are still PENDING, filled,
    and unclosed — regardless of what id list it is handed."""
    import tpt.engine.evaluator as ev

    db = await _make_db()
    cur = await db.cursor()
    await _insert_row(cur, "WAIT-USD")  # PENDING, not filled -> must stay
    await _insert_row(cur, "DONE-USD", status="LOSS", closed_at=int(time.time()))
    await _insert_row(cur, "LIVE-USD", filled_at=int(time.time()) - 30, fill_price=100.0)
    await db.commit()

    ids = [r[0] for r in await (await db.execute("SELECT id FROM signals")).fetchall()]
    monkeypatch.setattr(ev, "get_connection", lambda: _FakeConnCtx(db))

    # Same guarded UPDATE the evaluator's promotion step runs. db_write_lock is
    # held across awaits in production too, so exercising it around this
    # connection is the realistic shape.
    from tpt.db.write_lock import db_write_lock

    ph = ",".join("?" for _ in ids)
    async with db_write_lock:
        await db.execute(
            "UPDATE signals SET status='IN_TRADE' "
            "WHERE status='PENDING' AND filled_at IS NOT NULL "
            f"AND closed_at IS NULL AND id IN ({ph})",
            ids,
        )
        await db.commit()

    rows = {
        r["symbol"]: r["status"]
        for r in await (await db.execute("SELECT symbol, status FROM signals")).fetchall()
    }
    assert rows["WAIT-USD"] == "PENDING"
    assert rows["DONE-USD"] == "LOSS"
    assert rows["LIVE-USD"] == "IN_TRADE"
    await db.close()


@pytest.mark.asyncio
async def test_trades_endpoint_open_filter_and_total(monkeypatch):
    """/trades must expose IN_TRADE, expand OPEN to all three lifecycle
    stages, and report `total` for the whole filter (not just the page)."""
    from tpt.api.routes.backtest import list_trades

    db = await _make_db()
    cur = await db.cursor()
    ts = int(time.time()) - 300
    await _insert_row(cur, "AAA-USD")                                              # waiting
    await _insert_row(cur, "BBB-USD", status="IN_TRADE", filled_at=ts, fill_price=100.0)
    await _insert_row(cur, "CCC-USD", status="ACTIVE_T2", filled_at=ts, fill_price=100.0)
    await _insert_row(cur, "DDD-USD", status="WIN", closed_at=5, filled_at=1)
    await _insert_row(cur, "EEE-USD", status="IN_TRADE", filled_at=ts, fill_price=100.0,
                      pipeline_version="v3.1-gamma-pin-reversion")
    await db.commit()

    monkeypatch.setattr(
        "tpt.api.routes.backtest.get_connection", lambda: _FakeConnCtx(db)
    )

    res = await list_trades(status="OPEN", symbol=None, pipeline_version=None, scope="live", limit=200)
    assert res["count"] == 3
    assert res["total"] == 3
    assert {t["status"] for t in res["trades"]} == {"PENDING", "IN_TRADE", "ACTIVE_T2"}

    res = await list_trades(status="IN_TRADE", symbol=None, pipeline_version=None, scope="live", limit=200)
    # Live scope: only BBB — EEE belongs to a registered shadow pipeline.
    assert res["total"] == 1
    assert all(t["status"] == "IN_TRADE" for t in res["trades"])

    # ALL scope shows the shadow row too.
    res = await list_trades(status="IN_TRADE", symbol=None, pipeline_version=None, scope="all", limit=200)
    assert res["total"] == 2
    await db.close()


@pytest.mark.asyncio
async def test_stats_counts_and_pending_include_in_trade(monkeypatch):
    """Stats: IN_TRADE gets its own count bucket and feeds pending_count
    (open = waiting + in-trade + T2 tail)."""
    from tpt.api.routes.backtest import backtest_stats

    db = await _make_db()
    cur = await db.cursor()
    ts = int(time.time()) - 300
    await _insert_row(cur, "AAA-USD")
    await _insert_row(cur, "BBB-USD", status="IN_TRADE", filled_at=ts, fill_price=100.0)
    await _insert_row(cur, "CCC-USD", status="ACTIVE_T2", filled_at=ts, fill_price=100.0)
    await _insert_row(cur, "DDD-USD", status="WIN", closed_at=5, filled_at=1)
    await db.commit()

    monkeypatch.setattr(
        "tpt.api.routes.backtest.get_connection", lambda: _FakeConnCtx(db)
    )

    stats = await backtest_stats(pipeline_version=None, scope="live")
    assert stats["counts"]["IN_TRADE"] == 1
    assert stats["pending_count"] == 3  # PENDING + IN_TRADE + ACTIVE_T2
    assert stats["total_closed"] == 1
    assert len(stats["active"]) == 3
    await db.close()
