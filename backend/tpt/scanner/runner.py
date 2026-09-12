"""Scanner runner — orchestrates a full market scan.

Executes 2-phase scanning with rate limiting, candle optimization,
engine evaluation, and database persistence.

Write discipline
----------------
SQLite allows a single writer at a time, and every write in this module runs
inside `db_write_lock`. Two rules keep that lock cheap:

1. The ORM session's pending changes are **explicitly committed** — closing an
   AsyncSession without committing rolls the transaction back (which previously
   discarded every scan result).
2. The lock is **not held across network I/O**. All features/scores/ladders are
   computed into plain row dicts first; the lock is then taken once, briefly, to
   write everything. Holding it for the whole scan stalled every reader and
   writer for the scan's full duration.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select

from tpt.adapters.coinbase import CoinbaseAdapter
from tpt.config.settings import settings
from tpt.config.strategy import StrategyConfig, load_strategy
from tpt.data.database import get_connection
from tpt.db.connection import AsyncSessionLocal, init_db
from tpt.db.models import Feature, Ladder, ScanRun, Score, Snapshot, Symbol, new_uuid, utcnow_iso
from tpt.db.write_lock import db_write_lock
from tpt.engine.belief import FEATURE_VERSION, serialize_feature_vector
from tpt.engine.exits import TargetEstimate, calibrate_targets
from tpt.engine.features import FeatureDict, compute_features, multi_horizon_returns
from tpt.engine.labeler import compute_tags, label
from tpt.engine.ladder import compute_ladder, sanitize_ladder_dict
from tpt.engine.regime import beta_state_from_thrust, detect_regime, macro_thrust
from tpt.engine.scorer import ScoreBreakdown, score
from tpt.engine.ws_broadcaster import ui_stream
from tpt.engine.ws_memory import ws_memory

logger = logging.getLogger(__name__)


def _pick_direction(
    feats: FeatureDict,
    cfg: StrategyConfig,
    regime: str = "TRENDING_UP",
    macro_thrust: float = 0.0,
) -> tuple[str, ScoreBreakdown]:
    """Score both directions and pick one, with the trend guard.

    Shared by the triage passes and the final scoring pass so they agree on how a
    symbol would be traded — a disagreement would mean spending candle budget on
    symbols the final pass then reverses. The cheap pass has no candle data yet,
    so it estimates the macro push from BTC's 24h change alone; everything after
    the candle fetch uses the full thrust.
    """
    long_score = score(feats, cfg.scoring, trade_direction="LONG", regime=regime, macro_thrust=macro_thrust)
    short_score = score(feats, cfg.scoring, trade_direction="SHORT", regime=regime, macro_thrust=macro_thrust)

    day_chg = float(feats.get("day_change_pct") or 0.0)
    is_short_allowed = True
    if day_chg > 3.0 and (short_score["clamped"] - long_score["clamped"]) < 20.0:
        is_short_allowed = False

    if is_short_allowed and short_score["clamped"] > long_score["clamped"]:
        return "SHORT", short_score
    return "LONG", long_score


async def _calibrated_target() -> TargetEstimate:
    """Where should Target 1 sit? Answered from the ledger, not from a constant.

    Reads **closed** trades only. An open signal records zero excursion, which
    means "not measured yet" rather than "went nowhere", and feeding those in
    would drag every reach probability toward zero.
    """
    sql = (
        "SELECT entry_price, sl_price, mfe, mae FROM signals "
        "WHERE status IN ('WIN', 'LOSS', 'BREAK_EVEN', 'PARTIAL_WIN')"
    )
    try:
        async with get_connection() as conn, conn.execute(sql) as cur:
            rows = [dict(r) for r in await cur.fetchall()]
    except Exception as exc:
        logger.warning("Exit calibration read failed: %s", exc)
        return calibrate_targets([])

    return calibrate_targets(rows)


def extract_l2_vol(l2_book: dict[str, Any], spot_price: float) -> tuple[float, float]:
    """Sum USD liquidity within 2% of spot on each side of the book."""
    buy_vol = 0.0
    sell_vol = 0.0
    for b in l2_book.get("bids", []):
        p, s = float(b[0]), float(b[1])
        if p >= spot_price * 0.98:
            buy_vol += p * s
    for a in l2_book.get("asks", []):
        p, s = float(a[0]), float(a[1])
        if p <= spot_price * 1.02:
            sell_vol += p * s
    return buy_vol, sell_vol


@dataclass
class ScanRunResult:
    scan_run_id: str
    trigger: str
    symbols_fetched: int = 0
    symbols_stale: int = 0
    candidates_count: int = 0
    candidates: list[dict[str, Any]] = field(default_factory=list)
    status: str = "DONE"
    error_message: str | None = None
    duration_seconds: float | None = None


async def _persist_pending_signals(rows: list[tuple[Any, ...]]) -> None:
    """Insert backtest signals for newly-actionable setups, one transaction.

    Runs after the ORM block has committed, under the same write lock, so this
    raw connection never contends with an open ORM write transaction.
    """
    if not rows:
        return

    from tpt.data.database import get_connection

    four_hours_ago = int(time.time()) - (4 * 3600)
    # Kept as separate statements (not combined) so the write-lock scope is
    # explicit at a glance — it is the crux of SQLite write serialization.
    async with db_write_lock:  # noqa: SIM117
        async with get_connection() as conn:
            inserted = 0
            for row in rows:
                pid = row[1]
                async with conn.execute(
                    "SELECT id FROM signals WHERE symbol=? AND status='PENDING' AND CAST(timestamp AS INTEGER) > ?",
                    (pid, four_hours_ago),
                ) as cur:
                    already_exists = await cur.fetchone()
                if already_exists:
                    continue
                await conn.execute(
                    """INSERT INTO signals
                    (scan_run_id, symbol, timestamp, score, score_breakdown, label, trade_direction, entry_price, tp_price, tp2_price, sl_price, pipeline_version)
                    VALUES (?, ?, strftime('%s', 'now'), ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    row,
                )
                inserted += 1
            await conn.commit()
    if inserted:
        logger.info("Inserted %d new backtest signal(s).", inserted)


_scan_lock = asyncio.Lock()


def is_scan_running() -> bool:
    """True while a scan holds the scan lock."""
    return _scan_lock.locked()


async def run_scan(
    trigger: str = "ON_DEMAND",
    adapter: CoinbaseAdapter | None = None,
) -> ScanRunResult:
    """Run a market scan, refusing to overlap with a scan already in flight.

    Two concurrent scans double upstream API load and contend for SQLite's single
    write lock (the scheduled loop and a manual trigger could otherwise collide),
    so a second trigger is skipped rather than stacked.
    """
    if _scan_lock.locked():
        logger.warning("A scan is already in progress; skipping %s trigger.", trigger)
        return ScanRunResult(
            scan_run_id="",
            trigger=trigger,
            status="SKIPPED",
            error_message="A scan is already in progress.",
        )
    async with _scan_lock:
        return await _execute_scan(trigger=trigger, adapter=adapter)


async def _execute_scan(
    trigger: str = "ON_DEMAND",
    adapter: CoinbaseAdapter | None = None,
) -> ScanRunResult:
    """Execute a full market scan run. Callers must hold `_scan_lock`."""
    start_time = time.monotonic()
    await init_db()

    # Hot-reload strategy config per scan run (mtime-checked) so strategy.yaml
    # edits take effect without restarting the process.
    cfg = load_strategy()

    # Target calibration from realised excursions — Fix for the frozen win rate.
    #
    # The ladder placed T1 at a constant 2.0R derived from an R/R floor, while the
    # best favourable excursion ever recorded across 22 closed trades was 0.72R.
    # No trade could reach its target, so `WIN` was arithmetically impossible and
    # the edge page's 0% was a fact about the target, not about the market.
    #
    # Read once per scan: the estimate is a property of the ledger, not of any
    # single symbol.
    calibration = await _calibrated_target()
    target_r = calibration.r_multiple
    if target_r is not None:
        logger.info(
            "Exit calibration: T1 at %.2fR from %d closed trade(s) [%s]%s",
            target_r,
            calibration.n,
            "provisional" if calibration.provisional else "firm",
            f" — {calibration.reason}" if calibration.reason else "",
        )
    else:
        logger.info(
            "Exit calibration: no target published (n=%d) — T1 falls back to the 2.0R default. %s",
            calibration.n,
            calibration.reason or "",
        )

    own_adapter = adapter is None
    if adapter is None:
        adapter = CoinbaseAdapter()

    scan_run_id = new_uuid()
    started_at = utcnow_iso()

    # Record the RUNNING marker and read the watchlist (short critical section).
    async with db_write_lock, AsyncSessionLocal() as db:
        db.add(ScanRun(
            id=scan_run_id,
            trigger=trigger,
            started_at=started_at,
            status="RUNNING",
            config_snapshot=json.dumps(cfg.model_dump()),
        ))
        await db.commit()

        watchlist_res = await db.execute(
            select(Symbol.product_id).where(Symbol.on_watchlist == 1)
        )
        watchlist_set = set(watchlist_res.scalars().all())

    try:
        # 1. Fetch active USD spot products
        products = await adapter.get_products()
        logger.info("Fetched %d active USD product(s).", len(products) if products else 0)
        if not products:
            raise RuntimeError("No active USD products returned from exchange.")

        product_ids = [p["id"] for p in products]

        # 2. Phase 1: Fetch 24h stats for active products
        async def fetch_stats(pid: str) -> tuple[str, dict[str, Any] | None]:
            try:
                st = await adapter.get_stats(pid)
                return pid, st
            except Exception:
                return pid, None

        phase1_results = await asyncio.gather(*[fetch_stats(pid) for pid in product_ids])

        stats_map: dict[str, dict[str, Any]] = {}
        stale_symbols: set[str] = set()

        for pid, st in phase1_results:
            if st and isinstance(st, dict) and "last" in st:
                stats_map[pid] = st
            else:
                stale_symbols.add(pid)

        # 3. Cost-tiered triage, pass 1 — who earns the candle budget.
        #
        #    The previous filter was a hand-written rule over day_change and
        #    volume, which is how 91.5% of the universe ended up scored with no
        #    candle data at all: the brain was ranking symbols it had barely
        #    looked at. Instead, score every symbol on the features that are free
        #    (24h stats only) and buy candles for the strongest. Ranking on
        #    `rank_key` is the point — it shrinks a thinly-observed symbol toward
        #    neutral, so the budget goes to symbols the cheap features can
        #    actually speak to rather than to whatever moved most today.
        btc_stats = stats_map.get("BTC-USD")
        btc_day_change: float | None = None
        if btc_stats:
            b_open = float(btc_stats.get("open") or 0.0)
            b_last = float(btc_stats.get("last") or 0.0)
            if b_open > 0:
                btc_day_change = ((b_last - b_open) / b_open) * 100.0

        cheap_rank: list[tuple[float, str]] = []
        # Only BTC's 24h change is available before the candle fetch; the full
        # thrust (SMA distance plus day change) is computed once candles land.
        cheap_thrust = macro_thrust(btc_day_change_pct=btc_day_change)
        for pid in product_ids:
            if pid in stale_symbols:
                continue
            st = stats_map[pid]
            cheap_feats = compute_features(
                raw_stats=st,
                raw_ticker=st,
                btc_day_change_pct=btc_day_change,
            )
            cheap_feats["product_id"] = pid
            _cheap_dir, cheap_score = _pick_direction(
                cheap_feats, cfg, macro_thrust=cheap_thrust
            )
            cheap_rank.append((float(cheap_score["rank_key"]), pid))
        cheap_rank.sort(key=lambda t: t[0], reverse=True)

        candle_candidates: set[str] = {"BTC-USD"}
        candle_candidates.update(watchlist_set & set(stats_map))
        candle_candidates.update(pid for _key, pid in cheap_rank[: settings.candle_triage_top_k])

        btc_returns: dict[str, float] = {}

        # 4. Phase 2: multi-timeframe candles for candidates
        async def fetch_candles(pid: str) -> tuple[str, Any, Any, Any, Any]:
            # return_exceptions=True: a failure in ONE timeframe (e.g. an
            # unsupported granularity) must not discard the other three. With
            # return_exceptions=False a single failing request nullified the
            # entire candle pipeline for the symbol.
            results = await asyncio.gather(
                adapter.get_candles(pid, granularity=3600, limit=300),
                adapter.get_candles(pid, granularity=86400, limit=30),
                adapter.get_candles_15m(pid, limit=50),
                adapter.get_candles_6h(pid, limit=60),
                return_exceptions=True,
            )
            cleaned: list[Any] = [
                None if isinstance(r, BaseException) else r for r in results
            ]
            return (pid, cleaned[0], cleaned[1], cleaned[2], cleaned[3])

        phase2_results = await asyncio.gather(*[fetch_candles(pid) for pid in candle_candidates])
        candles_1h_map: dict[str, list[list[Any]]] = {}
        candles_1d_map: dict[str, list[list[Any]]] = {}
        candles_15m_map: dict[str, list[list[Any]]] = {}
        candles_6h_map: dict[str, list[list[Any]]] = {}

        for pid, c1h, c1d, c15m, c6h in phase2_results:
            if c1h is not None:
                candles_1h_map[pid] = c1h
            if c1d is not None:
                candles_1d_map[pid] = c1d
            if c15m is not None:
                candles_15m_map[pid] = c15m
            if c6h is not None:
                candles_6h_map[pid] = c6h

        # BTC's own multi-horizon returns: the benchmark every symbol's relative
        # strength is measured against, over identical windows.
        btc_returns = {
            k: v
            for k, v in multi_horizon_returns(
                candles_1h_map.get("BTC-USD"), candles_1d_map.get("BTC-USD")
            ).items()
            if v is not None
        }

        # 5. Phase 3: features, scoring, labeling, laddering.
        # No database session is open in this section, so the write lock is not
        # held across the scan's network I/O.
        candidates_out: list[dict[str, Any]] = []
        pending_signals: list[tuple[Any, ...]] = []
        telegram_alerts: list[dict[str, Any]] = []
        snapshot_rows: list[dict[str, Any]] = []
        feature_rows: list[dict[str, Any]] = []
        score_rows: list[dict[str, Any]] = []
        ladder_rows: list[dict[str, Any]] = []

        # 5b. Features for every symbol, in one pass. Symbols the triage bought
        #     candles for get the candle-derived components; the rest carry only
        #     stats-derived ones. That gap is no longer silent — it surfaces as
        #     `coverage` on the score, and as a lower `rank_key`.
        feats_map: dict[str, FeatureDict] = {}
        for pid in product_ids:
            if pid in stale_symbols:
                continue
            st = stats_map[pid]
            feats = compute_features(
                raw_stats=st,
                raw_ticker=st,
                raw_candles_1h=candles_1h_map.get(pid),
                raw_candles_1d=candles_1d_map.get(pid),
                btc_day_change_pct=btc_day_change,
                raw_candles_15m=candles_15m_map.get(pid),
                raw_candles_6h=candles_6h_map.get(pid),
                btc_returns=btc_returns,
            )
            feats["product_id"] = pid
            feats_map[pid] = feats

        current_regime = "TRENDING_UP"
        btc_feats = feats_map.get("BTC-USD")
        if btc_feats is not None:
            try:
                current_regime = detect_regime(btc_feats)
            except Exception as exc:
                logger.warning("Regime detection failed: %s", exc)

        # BTC's macro push as a signed percent, not a three-state flag. The scorer
        # prices it per symbol and per direction; the discrete label is kept only
        # so the log and stored history stay readable.
        btc_1h = candles_1h_map.get("BTC-USD")
        btc_closes_1h = [float(c[4]) for c in btc_1h if len(c) >= 5] if btc_1h else None
        beta_thrust = macro_thrust(btc_closes_1h, btc_day_change)
        logger.info(
            "Macro beta thrust %+.2f%% (%s); regime %s",
            beta_thrust, beta_state_from_thrust(beta_thrust), current_regime,
        )

        # 5c. Cost-tiered triage, pass 2 — who earns the enrichment budget.
        #
        #     Order-book, funding, open-interest and dealer-gamma lookups cost far
        #     more than candles, so they go to the strongest candidates only. The
        #     old gate was `comp_score >= 50` — the neutral baseline. A symbol had
        #     to already look average to be allowed the evidence that would show
        #     whether it was better than average: circular, and it capped the
        #     scorer at the very symbols it most needed to separate. Rank decides
        #     now, not a threshold on the thing being measured.
        pre_rank: list[tuple[float, str]] = []
        for pid, f in feats_map.items():
            _pre_dir, pre_score = _pick_direction(f, cfg, current_regime, beta_thrust)
            pre_rank.append((float(pre_score["rank_key"]), pid))
        pre_rank.sort(key=lambda t: t[0], reverse=True)

        enrich_set: set[str] = {p for p in watchlist_set if p in feats_map}
        enrich_set.update(pid for _key, pid in pre_rank[: settings.enrich_top_m])
        if "BTC-USD" in feats_map:
            enrich_set.add("BTC-USD")

        for pid in product_ids:
            if pid in stale_symbols:
                snapshot_rows.append({"product_id": pid, "is_stale": 1})
                continue

            feats = feats_map[pid]
            # `st` must be rebound here: the snapshot row below serialises it, and
            # without this it silently carried whatever symbol the previous loop
            # left behind, writing the SAME raw_stats for all 402 rows.
            st = stats_map[pid]
            c1h = candles_1h_map.get(pid)
            c1d = candles_1d_map.get(pid)
            pinned = (pid in watchlist_set)

            trade_direction, score_dict = _pick_direction(feats, cfg, current_regime, beta_thrust)
            comp_score = score_dict["clamped"]

            # --- Order-book / futures / options enrichment (triage-selected) ---
            if pid in enrich_set:
                try:
                    l2 = ws_memory.get_l2(pid)
                    if not l2 or not l2.get("bids"):
                        l2 = await adapter.get_l2_snapshot(pid)

                    last_p = float(feats["last_price"])
                    bids = l2.get("bids", [])
                    asks = l2.get("asks", [])

                    # Both sides of the book, symmetric 2% bands — matching the
                    # definition already used in features.py. Only the bid side
                    # was computed here, so `l2_resistance` (the SHORT direction's
                    # L2 component, weight 0.10) could never be backed and SHORT
                    # coverage was permanently capped at 0.90 while LONGs could
                    # reach 1.00.
                    feats["l2_buy_vol_2pct"] = sum(
                        float(b[1]) * float(b[0]) for b in bids if float(b[0]) >= last_p * 0.98
                    )
                    feats["l2_sell_vol_2pct"] = sum(
                        float(a[1]) * float(a[0]) for a in asks if float(a[0]) <= last_p * 1.02
                    )
                    feats["l2_bids"] = bids
                    feats["l2_asks"] = asks

                    # Institutional positioning (funding / open interest)
                    try:
                        from tpt.adapters.binance_futures import (
                            get_open_interest_hist,
                            get_premium_index,
                        )
                        b_sym = pid.split("-")[0] + "USDT"
                        fr = await get_premium_index(b_sym)
                        oi = await get_open_interest_hist(b_sym)
                        if fr:
                            feats["funding_rate"] = fr.get("funding_rate")
                        if oi:
                            feats["oi_change_pct"] = oi.get("oi_change_pct", 0.0)
                    except Exception as exc:
                        logger.debug("Futures metrics unavailable for %s: %s", pid, exc)

                    # Re-score now that the enrichment is actually in hand.
                    trade_direction, score_dict = _pick_direction(feats, cfg, current_regime, beta_thrust)
                    comp_score = score_dict["clamped"]
                except Exception as exc:
                    logger.warning("L2 validation failed for %s: %s", pid, exc)

            if score_dict.get("veto"):
                primary_label = "SKIP"
            else:
                primary_label = label(
                    feats, comp_score, cfg.labeling,
                    trade_direction=trade_direction,
                    regime=current_regime,
                )
            tags = compute_tags(feats, pinned=pinned)
            score_dict["tags"] = tags

            ladder_dict = compute_ladder(
                product_id=pid,
                features=feats,
                lbl=primary_label,
                composite_score=comp_score,
                config=cfg.ladder,
                pinned=pinned,
                trade_direction=trade_direction,
                regime=current_regime,
                # Calibrated from realised excursions at the top of this scan.
                target_r=target_r,
            )

            # Post-ladder refinement: promote to ENTRY_ZONE when price sits within
            # 0.75% of tranche A — but only if the setup actually clears the score
            # gate. Proximity alone used to be sufficient, which is how ENTRY_ZONE
            # became the single worst cohort in the ledger: 8 losses, 0 wins,
            # average score 31.9 against a configured minimum of 60. Proximity
            # says "the level is near". It says nothing about whether it is good.
            if ladder_dict and primary_label not in ("SKIP", "CHASE"):
                t_a = ladder_dict.get("tranche_a_price")
                current_price = feats.get("last_price")
                if t_a and current_price:
                    near_tranche_a = abs(float(current_price) - float(t_a)) / float(t_a) <= 0.0075
                    if near_tranche_a and comp_score >= cfg.labeling.entry_zone_score_min:
                        primary_label = "ENTRY_ZONE"
                    elif primary_label == "ENTRY_ZONE":
                        primary_label = "COILED"

            asyncio.create_task(ui_stream.broadcast({
                "event": "TICKER_SCORED",
                "product_id": pid,
                "label": primary_label,
                "score": round(comp_score, 2),
                "tags": tags,
                "ladder": ladder_dict,
            }))

            # --- Collect rows (written later, in one transaction) ---
            snapshot_rows.append({
                "product_id": pid,
                "raw_stats": json.dumps(st),
                "raw_ticker": json.dumps(st),
                "raw_candles_1h": json.dumps(c1h) if c1h else None,
                "raw_candles_1d": json.dumps(c1d) if c1d else None,
                "is_stale": 0,
            })

            feature_rows.append({
                "product_id": pid,
                "last_price": feats["last_price"],
                "day_open": feats["day_open"],
                "day_high": feats["day_high"],
                "day_low": feats["day_low"],
                "day_change_pct": feats["day_change_pct"],
                "pos_in_range": feats["pos_in_range"],
                "quote_vol_24h": feats["quote_vol_24h"],
                "vwap_24h": feats["vwap_24h"],
                "rsi_1h": feats["rsi_1h"],
                "rs_vs_btc": feats["rs_vs_btc"],
                "fib_236": feats["fib_236"],
                "fib_382": feats["fib_382"],
                "fib_500": feats["fib_500"],
                "fib_618": feats["fib_618"],
                "fib_786": feats["fib_786"],
                "swing_shelf_7d": feats["swing_shelf_7d"],
                "swing_high_7d": feats["swing_high_7d"],
                "vol_7d_avg_usd": feats["vol_7d_avg_usd"],
                # Flight recorder: the exact input set this score was computed
                # from, so the score can be replayed, audited or retrained later.
                "feature_vector": json.dumps(serialize_feature_vector(feats)),
                "feature_version": FEATURE_VERSION,
            })

            score_rows.append({
                "product_id": pid,
                "trade_direction": trade_direction,
                "composite_score": comp_score,
                "label": primary_label,
                "score_breakdown": json.dumps(score_dict),
                "edge": score_dict.get("edge"),
                "coverage": score_dict.get("coverage"),
                "rank_key": score_dict.get("rank_key"),
                "model_version": FEATURE_VERSION,
            })

            if ladder_dict:
                ladder_rows.append({
                    "product_id": pid,
                    "trade_direction": trade_direction,
                    "tranche_a_price": ladder_dict["tranche_a_price"],
                    "tranche_b_price": ladder_dict["tranche_b_price"],
                    "stop_price": ladder_dict["stop_price"],
                    "target_1_price": ladder_dict["target_1_price"],
                    "target_2_price": ladder_dict["target_2_price"],
                    "tranche_a_size_pct": ladder_dict["tranche_a_size_pct"],
                    "tranche_b_size_pct": ladder_dict["tranche_b_size_pct"],
                    "basis": json.dumps(ladder_dict["basis"]),
                    # Persist the calibrated T1 multiple. The read paths rebuild the
                    # ladder dict from this row before calling sanitize, which
                    # restores a 2.0R default if the field is missing.
                    "target_r": ladder_dict.get("target_r"),
                })

            candidates_out.append({
                "product_id": pid,
                "last_price": feats["last_price"],
                "day_change_pct": feats["day_change_pct"],
                "pos_in_range": feats["pos_in_range"],
                "quote_vol_24h": feats["quote_vol_24h"],
                "composite_score": comp_score,
                "edge": score_dict.get("edge"),
                "coverage": score_dict.get("coverage"),
                "coverage_band": score_dict.get("coverage_band"),
                "trade_direction": trade_direction,
                "label": primary_label,
                "tags": tags,
                "ladder": ladder_dict,
                "pinned": pinned,
            })

            # Queue backtest signal + alert for actionable setups
            if primary_label in ("ENTRY_ZONE", "COILED") and ladder_dict:
                san = sanitize_ladder_dict(ladder_dict)
                if san and san.get("tranche_a_price"):
                    pending_signals.append((
                        scan_run_id, pid, comp_score,
                        json.dumps(score_dict), primary_label, trade_direction,
                        san["tranche_a_price"],
                        san["target_1_price"],
                        san.get("target_2_price") or san["target_1_price"],
                        san["stop_price"],
                        "v2.0"
                    ))
                    telegram_alerts.append({
                        "symbol": pid,
                        "score": comp_score,
                        "label": primary_label,
                        "entry": san["tranche_a_price"],
                        "tp": san["target_1_price"],
                        "sl": san["stop_price"],
                    })

        # 6. Persist everything in one short critical section.
        duration = round(time.monotonic() - start_time, 2)

        # Kept as separate statements (not combined) so the write-lock scope is
        # explicit at a glance — it is the crux of SQLite write serialization.
        async with db_write_lock:  # noqa: SIM117
            async with AsyncSessionLocal() as db:
                # --- Symbol catalog upsert (single read, then add/update) ---
                existing_res = await db.execute(select(Symbol))
                existing = {s.product_id: s for s in existing_res.scalars().all()}
                seen_at = utcnow_iso()
                for p in products:
                    pid = p["id"]
                    sym = existing.get(pid)
                    if sym is None:
                        db.add(Symbol(
                            product_id=pid,
                            base_currency=p.get("base_currency", ""),
                            quote_currency=p.get("quote_currency", "USD"),
                            display_name=p.get("display_name", pid),
                            active=1,
                            on_watchlist=1 if pid in watchlist_set else 0,
                        ))
                    else:
                        sym.last_seen_at = seen_at
                        sym.active = 1
                await db.flush()

                # --- Bulk insert scan results ---
                db.add_all([Snapshot(scan_run_id=scan_run_id, **r) for r in snapshot_rows])
                db.add_all([Feature(scan_run_id=scan_run_id, **r) for r in feature_rows])
                db.add_all([Score(scan_run_id=scan_run_id, **r) for r in score_rows])
                db.add_all([Ladder(scan_run_id=scan_run_id, **r) for r in ladder_rows])

                # --- Alerts: zone entry / invalidation + watch lifecycle ---
                try:
                    from tpt.alerting.alerter import generate_alerts, persist_alerts
                    from tpt.db.models import Alert, Watch

                    watch_res = await db.execute(select(Watch).where(Watch.is_active == 1))
                    active_watches = {
                        (w.product_id, w.zone): {"product_id": w.product_id, "zone": w.zone}
                        for w in watch_res.scalars().all()
                    }

                    cutoff = (
                        datetime.now(UTC) - timedelta(hours=cfg.alerts.dedupe_hours)
                    ).isoformat()
                    dedupe_res = await db.execute(
                        select(Alert.dedupe_key).where(Alert.created_at >= cutoff)
                    )
                    recent_keys = set(dedupe_res.scalars().all())

                    alert_records = generate_alerts(
                        candidates_out,
                        active_watches,
                        cfg.alerts,
                        now_utc=datetime.now(UTC),
                        recent_dedupe_keys=recent_keys,
                    )
                    written = await persist_alerts(db, alert_records, scan_run_id)
                    if written:
                        logger.info("Recorded %d alert event(s).", written)
                except Exception as exc:
                    logger.warning("Alert generation failed: %s", exc)

                # === THE FIX: commit the scan results ===
                # Without this the AsyncSession closes and rolls back every
                # feature/score/ladder/snapshot added above.
                await db.commit()

                db_run = await db.get(ScanRun, scan_run_id)
                if db_run:
                    db_run.status = "DONE"
                    db_run.completed_at = utcnow_iso()
                    db_run.duration_seconds = duration
                    db_run.symbols_fetched = len(product_ids)
                    db_run.symbols_stale = len(stale_symbols)
                    db_run.candidates_count = len(candidates_out)
                    await db.commit()

        # Signals + Telegram run outside the ORM transaction (own connections).
        await _persist_pending_signals(pending_signals)

        for alert in telegram_alerts:
            try:
                from tpt.alerts.telegram import send_setup_alert
                await send_setup_alert(**alert)
            except Exception as exc:
                logger.warning("Telegram alert failed for %s: %s", alert["symbol"], exc)

        # --- Live L2 buffer management (bounded, prioritised) ---
        # Pinned symbols first, then the highest-scoring candidates, hard-capped:
        # three sockets per symbol otherwise exhausts the event loop.
        if settings.enable_live_ws:
            try:
                ranked = sorted(candidates_out, key=lambda c: c["composite_score"], reverse=True)
                desired = list(dict.fromkeys(
                    [*sorted(watchlist_set), *(c["product_id"] for c in ranked)]
                ))[: settings.max_ws_subscriptions]

                await ws_memory.sync_active_universe(desired)
                await ws_memory.subscribe(desired)
                logger.info("Live L2 buffer tracking %d symbol(s).", len(desired))
            except Exception as exc:
                logger.warning("Live L2 buffer management failed: %s", exc)
        else:
            logger.debug("Live L2 buffer disabled; scanner uses REST order-book snapshots.")

        if own_adapter:
            await adapter.close()

        sorted_candidates = sorted(
            candidates_out,
            key=lambda c: (0 if c["pinned"] else 1, -c["composite_score"])
        )

        duration = round(time.monotonic() - start_time, 2)
        return ScanRunResult(
            scan_run_id=scan_run_id,
            trigger=trigger,
            symbols_fetched=len(product_ids),
            symbols_stale=len(stale_symbols),
            candidates_count=len(sorted_candidates),
            candidates=sorted_candidates,
            status="DONE",
            duration_seconds=duration,
        )

    except Exception as exc:
        logger.exception("Scan %s failed", scan_run_id)
        duration = round(time.monotonic() - start_time, 2)
        try:
            async with db_write_lock, AsyncSessionLocal() as db:
                db_run = await db.get(ScanRun, scan_run_id)
                if db_run:
                    db_run.status = "FAILED"
                    db_run.error_message = str(exc)
                    db_run.completed_at = utcnow_iso()
                    db_run.duration_seconds = duration
                    await db.commit()
        except Exception as inner:
            logger.error("Could not record failure for scan %s: %s", scan_run_id, inner)

        if own_adapter:
            await adapter.close()

        return ScanRunResult(
            scan_run_id=scan_run_id,
            trigger=trigger,
            status="FAILED",
            error_message=str(exc),
            duration_seconds=duration,
        )
