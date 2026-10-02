"""Tests for the gamma payload's board-completeness fields.

The "0DTE share = 100%" artifact on the live board was a truncated chain:
Deribit WS reconnects drop every expiry except the nearest from the loaded
board while instrument metadata still covers the full chain. The payload now
reports how many expiries contributed to THIS computation (expiry_count) and
how many the fully-loaded chain should hold (chain_expiry_count, preferring
the gap-proof Deribit WS instrument universe), so a UI can detect a partial
board instead of publishing expiry-day captions off a one-expiry slice.
"""

import pytest

import tpt.adapters.deribit_ws as deribit_ws_module
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


def _stub_board(expiries):
    board = []
    for i, exp in enumerate(expiries):
        board.append(_contract(90.0 - i, "P", exp))
        board.append(_contract(110.0 + i, "C", exp))
    return board, {"active_venues": ["test"], "total_venues": 1,
                   "total_open_interest_usd": 1e8}


def _patch_aggregator(monkeypatch, stub):
    async def _fake(underlying):
        return stub(underlying)
    monkeypatch.setattr(
        options_flow_module, "aggregate_multi_venue_options_board", _fake)


@pytest.fixture(autouse=True)
def _clean_bucket_cache():
    options_flow_module._EXPIRY_BUCKET_CACHE.clear()
    yield
    options_flow_module._EXPIRY_BUCKET_CACHE.clear()


@pytest.mark.asyncio
async def test_full_board_reports_both_counts(monkeypatch):
    _patch_aggregator(
        monkeypatch, lambda u: _stub_board(["EXP1", "EXP2", "EXP3"]))
    res = await calculate_macro_gamma_exposure("XYZ", SPOT)
    assert res["options_available"] is True
    assert res["expiry_count"] == 3
    assert res["chain_expiry_count"] == 3


@pytest.mark.asyncio
async def test_partial_board_uses_ws_instrument_universe_as_reference(monkeypatch):
    """Only the nearest expiry's tickers arrived (reconnect gap), but the WS
    instrument universe still covers 6 expiries — the reference count must
    come from the seeds, not the truncated board."""
    _patch_aggregator(monkeypatch, lambda u: _stub_board(["EXP1"]))
    monkeypatch.setattr(
        deribit_ws_module, "expected_expiry_count", lambda u: 6)
    res = await calculate_macro_gamma_exposure("XYZ", SPOT)
    assert res["expiry_count"] == 1
    assert res["chain_expiry_count"] == 6


@pytest.mark.asyncio
async def test_no_ws_universe_falls_back_to_loaded_board(monkeypatch):
    """REST-only venues (or a WS board never seeded) report 0 from the
    helper — the loaded board's own count is the honest reference."""
    _patch_aggregator(
        monkeypatch, lambda u: _stub_board(["EXP1", "EXP2"]))
    monkeypatch.setattr(
        deribit_ws_module, "expected_expiry_count", lambda u: 0)
    res = await calculate_macro_gamma_exposure("XYZ", SPOT)
    assert res["expiry_count"] == 2
    assert res["chain_expiry_count"] == 2
