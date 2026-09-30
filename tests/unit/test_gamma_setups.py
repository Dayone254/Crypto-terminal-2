"""Tests for the gamma setup engine: evidence gates, the three setup
families' trigger geometry, and persistence isolation."""
import json

import pytest

import tpt.engine.gamma_setups as gs


def _ctx(**over):
    base = {
        "spot": 100000.0,
        "regime": "LONG_GAMMA_STABLE",
        "call_wall": 104000.0,
        "put_wall": 96000.0,
        "gamma_flip": 98500.0,
        "max_pain": 100500.0,
        "pin_map": [{"strike": 100000.0, "gex_m": 1.2, "dist_pct": 0.0, "strength": 100}],
        "confidence": {"score": 85, "grade": "A", "reasons": []},
        "computed_at": 0.0,
    }
    base.update(over)
    return base


# ---------------------------------------------------------------------------
# Evidence reader gates
# ---------------------------------------------------------------------------

def test_read_gamma_context_gates(monkeypatch):
    class FakeMem:
        def __init__(self, payload):
            self.payload = payload

        def get_macro_options(self, u):
            return self.payload

    good = {
        "underlying": "BTC", "options_available": True,
        "venue_metrics": {"active_venues": ["Deribit"]},
        "spot_price": 100000.0, "regime": "LONG_GAMMA_STABLE",
        "call_wall": 104000.0, "put_wall": 96000.0, "gamma_flip": 98500.0,
        "max_pain": 100500.0, "pin_map": [], "confidence": {"score": 85},
        "computed_at": 0.0,
    }
    fake = FakeMem(good)
    monkeypatch.setattr(gs, "ws_memory", fake)
    assert gs.read_gamma_context("BTC") is not None

    # Synthetic-only board must be refused
    syn = dict(good, venue_metrics={"active_venues": ["Synthetic GEX Engine"]})
    monkeypatch.setattr(gs, "ws_memory", FakeMem(syn))
    assert gs.read_gamma_context("BTC") is None

    # Low confidence refused
    low = dict(good, confidence={"score": 20})
    monkeypatch.setattr(gs, "ws_memory", FakeMem(low))
    assert gs.read_gamma_context("BTC") is None

    # Missing board refused
    monkeypatch.setattr(gs, "ws_memory", FakeMem(None))
    assert gs.read_gamma_context("BTC") is None


# ---------------------------------------------------------------------------
# Family triggers
# ---------------------------------------------------------------------------

def test_pin_reversion_fade_above_magnet():
    ctx = _ctx(max_pain=98500.0)  # spot 100000 -> +1.52% above the pin
    row = gs._setup_pin_reversion(ctx, "BTC", 100000.0)
    assert row is not None
    assert row["trade_direction"] == "SHORT"
    assert row["entry_price"] == 100000.0
    assert row["tp_price"] == 98500.0
    assert row["sl_price"] > row["entry_price"]
    note = json.loads(row["score_breakdown"])["note"]
    assert "max pain" in note


def test_pin_reversion_fade_below_magnet():
    ctx = _ctx(max_pain=102000.0)  # spot 100000 -> 1.96% below the pin
    row = gs._setup_pin_reversion(ctx, "BTC", 100000.0)
    assert row is not None
    assert row["trade_direction"] == "LONG"
    assert row["tp_price"] == 102000.0


def test_pin_reversion_requires_stretch():
    ctx = _ctx(max_pain=100300.0)  # 0.3% stretch: below the 1.2% gate
    assert gs._setup_pin_reversion(ctx, "BTC", 100000.0) is None


def test_pin_reversion_requires_long_gamma():
    ctx = _ctx(max_pain=98500.0, regime="SHORT_GAMMA_VOLATILE")
    assert gs._setup_pin_reversion(ctx, "BTC", 100000.0) is None


def test_pin_reversion_refuses_bad_geometry():
    # Max pain so close that R/R falls below 0.8 -> no row
    ctx = _ctx(max_pain=99600.0)  # 0.4% stretch, gate passed? no: <1.2
    ctx = _ctx(max_pain=98800.0)  # +1.21% stretch but reward 1200 vs risk 1200*... check
    row = gs._setup_pin_reversion(ctx, "BTC", 100000.0)
    # Either a coherent row or None — never an incoherent one
    if row is not None:
        risk = abs(row["entry_price"] - row["sl_price"])
        reward = abs(row["tp_price"] - row["entry_price"])
        assert reward / risk >= 0.8


def test_wall_rejection_short_at_call_wall():
    ctx = _ctx(spot=103700.0)  # 0.29% below call wall 104000, flip 98500 below spot
    row = gs._setup_wall_rejection(ctx, "BTC", 103700.0)
    assert row is not None
    assert row["trade_direction"] == "SHORT"
    assert row["tp_price"] == ctx["gamma_flip"]
    assert row["sl_price"] > 103700.0


def test_wall_rejection_long_at_put_wall():
    ctx = _ctx(spot=96300.0)  # 0.31% above put wall 96000, flip 98500 above spot
    row = gs._setup_wall_rejection(ctx, "BTC", 96300.0)
    assert row is not None
    assert row["trade_direction"] == "LONG"
    assert row["tp_price"] == ctx["gamma_flip"]


def test_wall_rejection_requires_long_gamma():
    ctx = _ctx(spot=103700.0, regime="SHORT_GAMMA_VOLATILE")
    assert gs._setup_wall_rejection(ctx, "BTC", 103700.0) is None


def test_flip_breakout_long_after_confirmed_flip():
    import time
    recent = {"ts": time.time() - 300, "from": "SHORT_GAMMA_VOLATILE",
              "to": "LONG_GAMMA_STABLE", "spot": 98600.0}

    class FakeTracker:
        def transitions(self, u):
            return [recent]

    import tpt.engine.gamma_analytics as ga
    orig = ga.get_regime_tracker
    ga.get_regime_tracker = lambda: FakeTracker()
    try:
        ctx = _ctx(spot=99000.0)  # spot above flip 98500
        row = gs._setup_flip_breakout(ctx, "BTC", 99000.0)
        assert row is not None
        assert row["trade_direction"] == "LONG"
        assert row["tp_price"] == 104000.0  # the call wall
    finally:
        ga.get_regime_tracker = orig


def test_flip_breakout_ignores_stale_flip():
    import time
    stale = {"ts": time.time() - 3 * 3600, "from": "SHORT_GAMMA_VOLATILE",
             "to": "LONG_GAMMA_STABLE", "spot": 98600.0}

    class FakeTracker:
        def transitions(self, u):
            return [stale]

    import tpt.engine.gamma_analytics as ga
    orig = ga.get_regime_tracker
    ga.get_regime_tracker = lambda: FakeTracker()
    try:
        ctx = _ctx(spot=99000.0)
        assert gs._setup_flip_breakout(ctx, "BTC", 99000.0) is None
    finally:
        ga.get_regime_tracker = orig


def test_flip_breakout_requires_directional_room():
    import time
    recent = {"ts": time.time() - 300, "from": "SHORT_GAMMA_VOLATILE",
              "to": "LONG_GAMMA_STABLE", "spot": 98600.0}

    class FakeTracker:
        def transitions(self, u):
            return [recent]

    import tpt.engine.gamma_analytics as ga
    orig = ga.get_regime_tracker
    ga.get_regime_tracker = lambda: FakeTracker()
    try:
        # Flip confirmed LONG but spot still BELOW the flip: no momentum yet
        ctx = _ctx(spot=98000.0)
        assert gs._setup_flip_breakout(ctx, "BTC", 98000.0) is None
    finally:
        ga.get_regime_tracker = orig


# ---------------------------------------------------------------------------
# Row assembly
# ---------------------------------------------------------------------------

def test_make_row_refuses_incoherent_rr():
    row = gs._make_row(
        pipeline_version=gs._PIN_REVERSION, symbol="BTC-USD", direction="LONG",
        spot=100000.0, stop=99900.0, target=100050.0,  # rr 0.5 < 0.8
        secondary=None, confidence={"score": 80}, regime="LONG_GAMMA_STABLE",
        setup_note="test",
    )
    assert row is None


def test_make_row_happy_path_shape():
    row = gs._make_row(
        pipeline_version=gs._WALL_REJECTION, symbol="ETH-USD", direction="SHORT",
        spot=3000.0, stop=3025.0, target=2950.0, secondary=2975.0,
        confidence={"score": 77}, regime="LONG_GAMMA_STABLE", setup_note="unit",
    )
    assert row is not None
    assert row["status"] == "PENDING"
    assert row["pipeline_version"] == "v3.1-gamma-wall-rejection"
    assert row["label"] == "GAMMA_WALL_REJECTION"
    bd = json.loads(row["score_breakdown"])
    assert bd["setup_family"] == "GAMMA_WALL_REJECTION"


# ---------------------------------------------------------------------------
# Persistence: dedup + write-lock discipline
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_persist_skips_duplicate_open_rows():
    """A second row for the same (pipeline, symbol) while one is open must be
    skipped, and the whole insert must go through the global write lock."""

    state = {"inserts": []}

    class FakeCursor:
        def __init__(self, sql):
            self.sql = sql

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        def __await__(self):
            async def _noop():
                return self
            return _noop().__await__()

        async def fetchone(self):
            return {"id": 1}  # an open row always "exists" -> skip

    class FakeConn:
        def execute(self, sql, params=None):
            if "INSERT INTO signals" in sql:
                state["inserts"].append(params)
            return FakeCursor(sql)

        async def commit(self):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

    class FakeLock:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

    import tpt.data.database as db_mod
    import tpt.db.write_lock as lock_mod

    def fake_get_connection():
        return FakeConn()

    monkey = getattr(gs, "_monkey", None)

    # Patch where the function imports from (call-time resolution).
    from _pytest.monkeypatch import MonkeyPatch
    mp = MonkeyPatch()
    mp.setattr(db_mod, "get_connection", fake_get_connection)
    mp.setattr(lock_mod, "db_write_lock", FakeLock())
    try:
        row = {
            "pipeline_version": "v3.1-gamma-pin-reversion", "symbol": "BTC-USD",
            "label": "GAMMA_PIN_REVERSION", "trade_direction": "SHORT", "score": 0.0,
            "score_breakdown": "{}", "entry_price": 1.0, "tp_price": 2.0,
            "tp2_price": 2.0, "sl_price": 0.5, "position_size_usd": 100.0,
            "status": "PENDING",
        }
        n = await gs._persist_gamma_signals([row, dict(row)])
        assert n == 0, "duplicate open rows must be skipped"
        assert state["inserts"] == [], "no INSERT may run while an open row exists"
    finally:
        mp.undo()


def test_pipeline_registry_constants():
    assert len(gs.GAMMA_PIPELINE_VERSIONS) == 3
    assert all(pv.startswith("v3.1-gamma-") for pv in gs.GAMMA_PIPELINE_VERSIONS)
    assert set(gs.FAMILIES_LABELS if hasattr(gs, "FAMILIES_LABELS") else gs.FAMILY_LABELS.values()) == {
        "GAMMA_PIN_REVERSION", "GAMMA_WALL_REJECTION", "GAMMA_FLIP_BREAKOUT",
    }
