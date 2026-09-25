"""Integration test for the cost-tiered triage and the flight recorder.

Verifies the two structural changes end to end against a mocked exchange:
  1. the candle budget is spent on a ranked shortlist, not the whole universe;
  2. every score carries (edge, coverage, rank_key) and every feature row carries
     the input vector it was computed from.
"""
from __future__ import annotations

import httpx
import pytest
from sqlalchemy import select

from tpt.adapters.coinbase import CoinbaseAdapter
from tpt.config.settings import settings
from tpt.db.connection import AsyncSessionLocal
from tpt.db.models import Feature, Score, Snapshot
from tpt.scanner.runner import run_scan

# Enough 1h candles for RSI(14), Bollinger(20) and volume ratio(21); enough daily
# candles for the 7d return that backs relative_strength.
_CANDLES = [
    [1725500000 + i * 3600, 0.0080 + i * 0.00001, 0.0088, 0.0081, 0.0085 + i * 0.00002, 5_000_000]
    for i in range(40)
]

_SYMBOLS = ["BTC", "AAA", "BBB", "CCC", "DDD", "EEE", "FFF", "GGG", "HHH", "III"]


@pytest.fixture
def counted_adapter() -> tuple[CoinbaseAdapter, set[str]]:
    products = [
        {"id": f"{sym}-USD", "base_currency": sym, "quote_currency": "USD",
         "status": "online", "trading_disabled": False}
        for sym in _SYMBOLS
    ]
    # Stats must differ per symbol, otherwise a snapshot that wrongly repeats one
    # symbol's stats for every row would be indistinguishable from a correct one.
    def stats_for(sym: str) -> dict:
        i = _SYMBOLS.index(sym) + 1
        return {"open": f"{100.0 + i}", "high": f"{110.0 + i}", "low": "90.0",
                "last": f"{105.0 + i}", "volume": "200000"}
    candle_symbols: set[str] = set()

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/products":
            return httpx.Response(200, json=products)
        if path.endswith("/stats") or path.endswith("/ticker"):
            sym = path.split("/")[2].split("-")[0]
            return httpx.Response(200, json=stats_for(sym))
        if "/candles" in path:
            symbol = path.split("/")[2]
            candle_symbols.add(symbol)
            # Give each symbol a distinct close series so candle features differ.
            bump = (_SYMBOLS.index(symbol.split("-")[0]) + 1) * 0.00001
            series = [[t, lo + bump, hi + bump, o + bump, cl + bump, vol]
                      for t, lo, hi, o, cl, vol in _CANDLES]
            return httpx.Response(200, json=series)
        if "/book" in path:
            return httpx.Response(200, json={
                "bids": [["104.0", "5000", 3]], "asks": [["106.0", "5000", 3]],
            })
        return httpx.Response(404)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return CoinbaseAdapter(client=client), candle_symbols


@pytest.mark.asyncio
async def test_candle_budget_is_capped_and_coverage_is_reported(
    counted_adapter: tuple[CoinbaseAdapter, set[str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    adapter, candle_symbols = counted_adapter
    monkeypatch.setattr(settings, "candle_triage_top_k", 3)
    monkeypatch.setattr(settings, "enrich_top_m", 1)

    try:
        res = await run_scan(trigger="ON_DEMAND", adapter=adapter)
        assert res.status == "DONE"
        assert res.symbols_fetched == len(_SYMBOLS)

        # 1. The budget is a shortlist, not the universe. BTC is always included
        #    regardless of rank, so allow for top_k + 1.
        assert len(candle_symbols) <= 4, f"triage overspent: {sorted(candle_symbols)}"
        assert len(candle_symbols) < len(_SYMBOLS), "triage bought candles for everyone"

        # 2. Belief state is persisted on every score.
        async with AsyncSessionLocal() as db:
            scores = (await db.execute(
                select(Score).where(Score.scan_run_id == res.scan_run_id)
            )).scalars().all()
            assert len(scores) == len(_SYMBOLS)
            for s in scores:
                assert s.coverage is not None, f"{s.product_id} has no coverage"
                assert s.edge is not None, f"{s.product_id} has no edge"
                assert s.rank_key is not None, f"{s.product_id} has no rank_key"

            # Symbols that got candles report strictly more coverage than those
            # that did not — that gap is the whole point. With 40 candles every
            # candle-derived component is backed, giving three populations:
            #   0.35  liquidity + trend                     (neither pass)
            #   0.45  liquidity + trend + order book        (enriched, no candles)
            #   0.90  everything but the order book         (candles)
            #   1.00  everything                            (both passes)
            # 0.45 is legitimate: the enrichment shortlist is ranked on
            # candle-aware features, so it can reach a symbol the candle budget
            # skipped. Coverage reports what actually happened rather than what
            # the design hoped for, which is the point of having it at all.
            covs = sorted(round(s.coverage, 2) for s in scores)
            assert covs[-1] >= 0.90, f"no symbol reached full candle coverage: {covs}"
            assert covs[0] == 0.35, f"untriaged coverage should be 0.35: {covs}"
            assert set(covs) <= {0.35, 0.45, 0.90, 1.0}, f"unexpected coverage values: {covs}"

            triaged = sum(1 for c in covs if c >= 0.90)
            assert 0 < triaged < len(covs), "triage did not split the universe"

            # A thinly-observed symbol must not outrank a fully-observed one on
            # coverage-adjusted rank alone.
            best_thin = max((s.rank_key for s in scores if s.coverage < 0.60), default=0.0)
            assert best_thin < 50.0 + 50.0 * 0.60 + 15.0, "thin score exceeded its ceiling"

            # 3. Flight recorder: the inputs behind each score are stored.
            feats = (await db.execute(
                select(Feature).where(Feature.scan_run_id == res.scan_run_id)
            )).scalars().all()
            assert len(feats) == len(_SYMBOLS)
            for f in feats:
                assert f.feature_vector, f"{f.product_id} has no recorded input vector"
                assert f.feature_version, f"{f.product_id} has no feature version"

            # 4. Regression: each snapshot must carry ITS OWN stats. Restructuring
            #    the scan loop once dropped the per-symbol rebinding, so every row
            #    serialised the previous loop's leftover and all 402 snapshots
            #    ended up with identical raw_stats.
            snaps = (await db.execute(
                select(Snapshot).where(Snapshot.scan_run_id == res.scan_run_id)
            )).scalars().all()
            assert len(snaps) == len(_SYMBOLS)
            assert len({s.raw_stats for s in snaps}) == len(_SYMBOLS), (
                "snapshots are carrying duplicated raw_stats"
            )
            assert len({s.raw_ticker for s in snaps}) == len(_SYMBOLS), (
                "snapshots are carrying duplicated raw_ticker"
            )
    finally:
        await adapter.close()
