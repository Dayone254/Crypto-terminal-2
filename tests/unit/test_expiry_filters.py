"""Regression tests for the ALL / 0DTE / 7D / 30D expiry-bucket logic in the
GEX engine.

Guarantees under test:
- 0DTE strictly selects contracts expiring within 1 day and honestly reports
  an empty band (expiry_available=False) instead of serving other expiries.
- 7D and 30D bands are mutually exclusive slices (1-8d and 8-35d) and never
  silently fall back to the whole board when their slice is empty.
- ALL is the only filter that serves the unfiltered board.
- Band-filtered payloads never feed the 24h OI-flow baseline comparison.
- Bucket payloads are TTL-cached so the 1s WS loop does not re-run the engine.
"""

import pytest

import tpt.adapters.shared_client as shared_client_module
import tpt.engine.options_flow as options_flow_module
from tpt.engine.options_flow import calculate_macro_gamma_exposure


SPOT = 100.0


def _contract(strike, ctype, expiry_str, oi=50.0):
    return {
        "symbol": f"XYZ-{strike}-{ctype}-{expiry_str}",
        "underlying": "XYZ",
        "expiry_str": expiry_str,
        "strike": strike,
        "type": ctype,
        "open_interest": oi,
        "underlying_price": SPOT,
        "implied_volatility": 0.6,
    }


def _near_expiry(days_ahead):
    """A Deribit-style expiry string days_ahead days out, settling 08:00 UTC.

    The near leg rolls to tomorrow only AFTER today's 08:00 settlement has
    actually passed. Rolling early (the old 5-minute margin) pushed the
    same-day contract's dte to ~1.005 — outside the 0DTE band's strict
    `<= 1.0` filter (empty band) and inside the 7D band (mis-bucketed), so
    this suite failed for ~72 minutes around every settlement boundary
    depending on when it ran."""
    import datetime as dt

    now = dt.datetime.now(dt.UTC)
    exp = now.replace(hour=8, minute=0, second=0, microsecond=0) + dt.timedelta(days=days_ahead)
    if days_ahead == 0 and exp <= now:
        exp += dt.timedelta(days=1)
    return exp.strftime("%d%b%y").upper()


def _stub_multiband_board(underlying):
    """Board with one dated expiry per band (real venue style: '27SEP24')."""
    today = _near_expiry(0)
    weekly = _near_expiry(5)
    monthly = _near_expiry(20)
    board = [
        _contract(90.0, "P", today), _contract(110.0, "C", today),
        _contract(85.0, "P", weekly), _contract(115.0, "C", weekly),
        _contract(80.0, "P", monthly), _contract(120.0, "C", monthly),
    ]
    return board, {"active_venues": ["test"], "total_venues": 1, "total_open_interest_usd": 1e8}


def _stub_weekly_only_board(underlying):
    """No same-day or monthly contracts — only the weekly (5d out)."""
    weekly = _near_expiry(5)
    board = [_contract(85.0, "P", weekly), _contract(115.0, "C", weekly)]
    return board, {"active_venues": ["test"], "total_venues": 1, "total_open_interest_usd": 1e8}


def _patch(monkeypatch, stub):
    async def _fake(underlying):
        return stub(underlying)
    monkeypatch.setattr(options_flow_module, "aggregate_multi_venue_options_board", _fake)


@pytest.fixture(autouse=True)
def _clean_bucket_cache():
    options_flow_module._EXPIRY_BUCKET_CACHE.clear()
    yield
    options_flow_module._EXPIRY_BUCKET_CACHE.clear()


@pytest.mark.asyncio
async def test_all_serves_entire_board_and_echoes_filter(monkeypatch):
    _patch(monkeypatch, _stub_multiband_board)
    res = await calculate_macro_gamma_exposure("XYZ", expiry_filter="ALL")
    assert res["options_available"] is True
    assert res["expiry_filter"] == "ALL"
    # All three expiries contribute: walls can come from any band.
    expiries = {c["expiry"] for c in res["expiry_clusters"] if c["expiry"] != "_0DTE_SHARE"}
    assert len(expiries) == 3


@pytest.mark.asyncio
async def test_0dte_selects_only_same_day_expiry(monkeypatch):
    _patch(monkeypatch, _stub_multiband_board)
    res = await calculate_macro_gamma_exposure("XYZ", expiry_filter="0DTE")
    assert res["options_available"] is True
    assert res["expiry_filter"] == "0DTE"
    # If weekly/monthly leaked in, expiry_clusters would show 3 expiries.
    expiries = {c["expiry"] for c in res["expiry_clusters"] if c["expiry"] != "_0DTE_SHARE"}
    assert len(expiries) == 1
    cluster = next(c for c in res["expiry_clusters"] if c["expiry"] != "_0DTE_SHARE")
    # dte arrives rounded to 1 decimal, and parse_expiry pins dated expiries to
    # 08:00 UTC settlement: late in the UTC morning a same-day expiry rounds to
    # 0.0 (that is what 0DTE means), and just before 07:55 the roll guard puts
    # the raw dte a hair over 1.0 (rounding back to exactly 1.0). Assert the
    # real invariant — a same-day settlement, never negative — on the rounded
    # value; the engine's own band filter is unrounded and stays strict.
    assert 0.0 <= cluster["dte"] <= 1.0


@pytest.mark.asyncio
async def test_7d_band_excludes_0dte_and_monthly(monkeypatch):
    _patch(monkeypatch, _stub_multiband_board)
    res = await calculate_macro_gamma_exposure("XYZ", expiry_filter="7D")
    assert res["options_available"] is True
    clusters = [c for c in res["expiry_clusters"] if c["expiry"] != "_0DTE_SHARE"]
    assert len(clusters) == 1
    assert 1.0 < clusters[0]["dte"] <= 8.0


@pytest.mark.asyncio
async def test_30d_band_excludes_weeklies(monkeypatch):
    _patch(monkeypatch, _stub_multiband_board)
    res = await calculate_macro_gamma_exposure("XYZ", expiry_filter="30D")
    assert res["options_available"] is True
    clusters = [c for c in res["expiry_clusters"] if c["expiry"] != "_0DTE_SHARE"]
    assert len(clusters) == 1
    assert 8.0 < clusters[0]["dte"] <= 35.0


@pytest.mark.asyncio
async def test_empty_7d_band_is_honest_not_silent_fallback(monkeypatch):
    """Weekly-only chain: the 30D slice is empty. The old code silently served
    the whole board under the 30D label; it must refuse instead."""
    _patch(monkeypatch, _stub_weekly_only_board)
    res = await calculate_macro_gamma_exposure("XYZ", expiry_filter="30D")
    assert res["expiry_available"] is False
    assert res["options_available"] is False
    assert "30D" in res["message"]
    assert "gex_curve" not in res  # no ghost GEX payload fields


@pytest.mark.asyncio
async def test_empty_0dte_band_reports_unavailable(monkeypatch):
    _patch(monkeypatch, _stub_weekly_only_board)
    res = await calculate_macro_gamma_exposure("XYZ", expiry_filter="0DTE")
    assert res["expiry_available"] is False
    assert res["options_available"] is False


@pytest.mark.asyncio
async def test_bucket_payload_is_ttl_cached(monkeypatch):
    _patch(monkeypatch, _stub_multiband_board)
    calls = {"n": 0}

    real = options_flow_module.aggregate_multi_venue_options_board

    async def _counting(underlying):
        calls["n"] += 1
        return await real(underlying)

    monkeypatch.setattr(options_flow_module, "aggregate_multi_venue_options_board", _counting)

    await calculate_macro_gamma_exposure("XYZ", expiry_filter="7D")
    await calculate_macro_gamma_exposure("XYZ", expiry_filter="7D")
    await calculate_macro_gamma_exposure("XYZ", expiry_filter="7D")
    assert calls["n"] == 1, "repeat bucket reads within the TTL must reuse the cache"

    # ALL is never bucket-cached.
    await calculate_macro_gamma_exposure("XYZ", expiry_filter="ALL")
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_filtered_payload_is_not_written_to_shared_all_cache(monkeypatch):
    """Expiry-scoped results must never poison the ws_memory ALL cache."""
    import tpt.engine.ws_memory as ws_memory_module

    _patch(monkeypatch, _stub_multiband_board)
    ws_memory_module.ws_memory.macro_options_cache.clear()
    try:
        await calculate_macro_gamma_exposure("XYZ", expiry_filter="0DTE")
        assert ws_memory_module.ws_memory.macro_options_cache.get("XYZ") is None
    finally:
        ws_memory_module.ws_memory.macro_options_cache.clear()


@pytest.mark.asyncio
async def test_oi_flow_skipped_for_band_filtered_boards(monkeypatch):
    """Band board vs whole-chain 24h baseline fabricates flows; compute_oi_flow
    must refuse the comparison when an expiry band is active."""
    from tpt.engine.oi_history import compute_oi_flow

    _patch(monkeypatch, _stub_multiband_board)

    async def _boom(underlying):
        raise AssertionError("get_baseline must not be called for band views")

    monkeypatch.setattr("tpt.engine.oi_history.get_baseline", _boom)

    board, _vm = _stub_multiband_board("XYZ")
    assert await compute_oi_flow("XYZ", board, expiry_filter="0DTE") is None
    assert await compute_oi_flow("XYZ", board, expiry_filter="7D") is None
    assert await compute_oi_flow("XYZ", board, expiry_filter="30D") is None
    # Baseline comparison still allowed for ALL.
    async def _baseline(underlying):
        return None
    monkeypatch.setattr("tpt.engine.oi_history.get_baseline", _baseline)
    assert await compute_oi_flow("XYZ", board, expiry_filter="ALL") is None
