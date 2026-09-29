"""Regression tests for the GEX engine's fallback discipline.

History: when an underlying had no options board (every altcoin), the engine
fell through to a hardcoded BTC spot price (85875.50) and built a synthetic
options board anchored to it — so BTC-scale gamma levels were served for
PUMP-USD and friends, rendered on altcoin charts and fed into altcoin scoring
inputs (iv_skew, gamma_wall_proximity). The engine now returns an honest
"options unavailable" payload unless the caller explicitly opts into the
synthetic board (BTC/ETH desk regime panel only).
"""

import pytest

import tpt.adapters.shared_client as shared_client_module
import tpt.engine.options_flow as options_flow_module
from tpt.engine.options_flow import calculate_macro_gamma_exposure

BTC_PRICE = "85875.50"
SUBPENNY_PRICE = "0.00516900"


def _stub_no_board(underlying):
    return [], {"active_venues": [], "total_venues": 0}


def _stub_real_board(underlying):
    common = {"underlying": underlying, "underlying_price": 100.0, "implied_volatility": 0.6}
    board = [
        {"symbol": f"{underlying}-90-P-7D", "expiry_str": "7D", "strike": 90.0,
         "type": "P", "open_interest": 50.0, **common},
        {"symbol": f"{underlying}-110-C-7D", "expiry_str": "7D", "strike": 110.0,
         "type": "C", "open_interest": 50.0, **common},
    ]
    return board, {"active_venues": ["test"], "total_venues": 1}


def _patch_aggregator(monkeypatch, stub):
    async def _fake(underlying):
        return stub(underlying)
    monkeypatch.setattr(options_flow_module, "aggregate_multi_venue_options_board", _fake)


def _patch_spot_feed(monkeypatch, price: str, calls: list | None = None):
    class _Resp:
        status_code = 200

        def json(self):
            return {"price": price}

    class _Client:
        async def get(self, *args, **kwargs):
            if calls is not None:
                calls.append(args[0] if args else "")
            return _Resp()

    monkeypatch.setattr(shared_client_module, "get_shared_client", lambda: _Client())


@pytest.mark.asyncio
async def test_altcoin_without_board_returns_unavailable_by_default(monkeypatch):
    """PUMP has no options market: the payload must say so instead of
    inventing BTC-scale levels."""
    _patch_aggregator(monkeypatch, _stub_no_board)
    network_calls: list = []
    _patch_spot_feed(monkeypatch, BTC_PRICE, network_calls)

    res = await calculate_macro_gamma_exposure("PUMP")

    assert res["options_available"] is False
    assert res["regime"] == "UNAVAILABLE"
    assert res["gamma_flip"] is None
    assert res["call_wall"] is None
    assert res["put_wall"] is None
    assert res["gamma_walls"] == []
    assert res["gex_curve"] == []
    # The honest exit fires before any spot fetch is attempted.
    assert network_calls == []


@pytest.mark.asyncio
async def test_btc_empty_board_uses_synthetic_and_btc_scale(monkeypatch):
    """Opt-in synthetic fallback (majors only) still anchors to the real spot."""
    _patch_aggregator(monkeypatch, _stub_no_board)
    _patch_spot_feed(monkeypatch, BTC_PRICE)

    res = await calculate_macro_gamma_exposure("BTC", allow_synthetic=True)

    assert res["options_available"] is True
    assert res["spot_price"] == pytest.approx(85875.50)
    assert 50_000 < res["gamma_flip"] < 120_000
    assert res["call_wall"] > res["spot_price"]
    assert res["put_wall"] < res["spot_price"]
    assert res["gamma_walls"], "synthetic board should produce gamma walls"


@pytest.mark.asyncio
async def test_synthetic_grid_tracks_subpenny_spot(monkeypatch):
    """The strike quantizer must follow the instrument's magnitude: a sub-penny
    spot produces sub-penny strikes (the old fixed-multiplier grid collapsed
    everything below $0.50 onto one strike, and anything anchored to a wrong
    spot landed in another price domain entirely)."""
    _patch_aggregator(monkeypatch, _stub_no_board)
    _patch_spot_feed(monkeypatch, SUBPENNY_PRICE)

    res = await calculate_macro_gamma_exposure("PUMP", allow_synthetic=True)

    assert res["options_available"] is True
    assert res["spot_price"] == pytest.approx(0.005169)
    assert 0.003 < res["call_wall"] < 0.008
    assert 0.003 < res["put_wall"] < 0.008
    assert res["call_wall"] > res["put_wall"]
    curve_strikes = [c["strike"] for c in res["gex_curve"]]
    assert curve_strikes and max(curve_strikes) < 0.01


@pytest.mark.asyncio
async def test_real_board_passes_through_without_synthetic(monkeypatch):
    """A real options board is processed normally with synthetic disabled."""
    _patch_aggregator(monkeypatch, _stub_real_board)

    res = await calculate_macro_gamma_exposure("XYZ")

    assert res["options_available"] is True
    assert res["spot_price"] == pytest.approx(100.0)
    assert res["call_wall"] == pytest.approx(110.0)
    assert res["put_wall"] == pytest.approx(90.0)
    assert 85.0 <= res["gamma_flip"] <= 115.0
    assert res["regime"] in ("LONG_GAMMA_STABLE", "SHORT_GAMMA_VOLATILE")
