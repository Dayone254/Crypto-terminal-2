"""Scanner runner — orchestrates a full market scan.

Executes 2-phase scanning with rate limiting, candle optimization,
engine evaluation, and database persistence.

Write discipline
----------------
SQLite allows a single writer at a time. Every write in this module runs inside
`db_write_lock`, and the ORM session's pending changes are **explicitly
committed** — closing an AsyncSession without committing rolls the transaction
back, which silently discarded every scan result.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select

from tpt.adapters.coinbase import CoinbaseAdapter
from tpt.config.strategy import load_strategy
from tpt.db.connection import AsyncSessionLocal, init_db
from tpt.db.models import Feature, Ladder, ScanRun, Score, Snapshot, Symbol, new_uuid, utcnow_iso
from tpt.db.write_lock import db_write_lock
from tpt.engine.features import compute_features
from tpt.engine.labeler import compute_tags, label
from tpt.engine.ladder import compute_ladder, sanitize_ladder_dict
from tpt.engine.scorer import score
from tpt.engine.ws_broadcaster import ui_stream
from tpt.engine.ws_memory import ws_memory

logger = logging.getLogger(__name__)


def extract_l2_vol(l2_book: dict[str, Any], spot_price: float) -> tuple[float, float]:
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
    async with db_write_lock:
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
                    (scan_run_id, symbol, timestamp, score, score_breakdown, label, trade_direction, entry_price, tp_price, tp2_price, sl_price)
                    VALUES (?, ?, strftime('%s', 'now'), ?, ?, ?, ?, ?, ?, ?, ?)""",
                    row,
                )
                inserted += 1
            await conn.commit()
    if inserted:
        logger.info("Inserted %d new backtest signal(s).", inserted)


async def run_scan(
    trigger: str = "ON_DEMAND",
    adapter: CoinbaseAdapter | None = None,
) -> ScanRunResult:
    """Execute a full market scan run."""
    start_time = time.monotonic()
    await init_db()

    # Hot-reload strategy config per scan run (mtime-checked) so strategy.yaml
    # edits take effect without restarting the process.
    cfg = load_strategy()

    own_adapter = adapter is None
    if adapter is None:
        adapter = CoinbaseAdapter()

    scan_run_id = new_uuid()
    started_at = utcnow_iso()

    async with AsyncSessionLocal() as db:
        scan_run = ScanRun(
            id=scan_run_id,
            trigger=trigger,
            started_at=started_at,
            status="RUNNING",
            config_snapshot=json.dumps(cfg.model_dump()),
        )
        db.add(scan_run)
        await db.commit()

        watchlist_res = await db.execute(select(Symbol.product_id).where(Symbol.on_watchlist == 1))
        watchlist_set = set(watchlist_res.scalars().all())

    try:
        # 1. Fetch active USD spot products
        products = await adapter.get_products()
        logger.info("Fetched %d active USD product(s).", len(products) if products else 0)
        if not products:
            raise RuntimeError("No active USD products returned from exchange.")

        product_ids = [p["id"] for p in products]

        # Lock the WS background buffer onto the active watchlist universe
        if watchlist_set:
            asyncio.create_task(ws_memory.subscribe(list(watchlist_set)))

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

        # 3. Identify Phase 2 candle candidates from stats alone
        btc_stats = stats_map.get("BTC-USD")
        btc_day_change: float | None = None
        if btc_stats:
            b_open = float(btc_stats.get("open") or 0.0)
            b_last = float(btc_stats.get("last") or 0.0)
            if b_open > 0:
                btc_day_change = ((b_last - b_open) / b_open) * 100.0

        min_vol = cfg.labeling.min_quote_volume
        candle_candidates: set[str] = {"BTC-USD"}

        await ws_memory.sync_active_universe(product_ids)

        for pid in product_ids:
            if pid in stale_symbols:
                continue
            st = stats_map[pid]
            last = float(st.get("last") or st.get("price") or 0.0)
            open_p = float(st.get("open") or last)
            high_p = float(st.get("high") or last)
            low_p = float(st.get("low") or last)
            vol_base = float(st.get("volume") or 0.0)
            quote_vol = vol_base * last

            # Always fetch candles for pinned symbols
            if pid in watchlist_set:
                candle_candidates.add(pid)
                continue

            if quote_vol >= min_vol:
                day_change = ((last - open_p) / open_p) * 100.0 if open_p > 0 else 0.0
                pos_in_range = (last - low_p) / (high_p - low_p) if high_p > low_p else 0.5
                is_chase = (day_change > 15.0 and pos_in_range > 0.80)
                if not is_chase and (-3.0 <= day_change <= 8.0 or day_change > 2.0 or quote_vol >= 5_000_000.0):
                    candle_candidates.add(pid)

        # 4. Phase 2: multi-timeframe candles for candidates
        async def fetch_candles(pid: str) -> tuple[str, Any, Any, Any, Any]:
            try:
                c1h, c1d, c15m, c4h = await asyncio.gather(
                    adapter.get_candles(pid, granularity=3600, limit=300),
                    adapter.get_candles(pid, granularity=86400, limit=30),
                    adapter.get_candles_15m(pid, limit=50),
                    adapter.get_candles_4h(pid, limit=60),
                    return_exceptions=False,
                )
                return pid, c1h, c1d, c15m, c4h
            except Exception:
                return pid, None, None, None, None

        phase2_results = await asyncio.gather(*[fetch_candles(pid) for pid in candle_candidates])
        candles_1h_map: dict[str, list[list[Any]]] = {}
        candles_1d_map: dict[str, list[list[Any]]] = {}
        candles_15m_map: dict[str, list[list[Any]]] = {}
        candles_4h_map: dict[str, list[list[Any]]] = {}

        for pid, c1h, c1d, c15m, c4h in phase2_results:
            if c1h is not None:
                candles_1h_map[pid] = c1h
            if c1d is not None:
                candles_1d_map[pid] = c1d
            if c15m is not None:
                candles_15m_map[pid] = c15m
            if c4h is not None:
                candles_4h_map[pid] = c4h

        # 5. Phase 3: features, scoring, labeling, laddering
        candidates_out: list[dict[str, Any]] = []
        pending_signals: list[tuple[Any, ...]] = []
        telegram_alerts: list[dict[str, Any]] = []

        from tpt.engine.regime import detect_regime
        current_regime = "TRENDING_UP"
        if "BTC-USD" in stats_map:
            try:
                st_btc = stats_map["BTC-USD"]
                btc_feats = compute_features(
                    raw_stats=st_btc,
                    raw_ticker=st_btc,
                    raw_candles_1h=candles_1h_map.get("BTC-USD"),
                    raw_candles_1d=candles_1d_map.get("BTC-USD"),
                    btc_day_change_pct=None,
                    raw_candles_15m=candles_15m_map.get("BTC-USD"),
                    raw_candles_4h=candles_4h_map.get("BTC-USD"),
                )
                current_regime = detect_regime(btc_feats)
            except Exception as exc:
                logger.warning("Regime detection failed: %s", exc)

        async with db_write_lock:
            async with AsyncSessionLocal() as db:
                # --- Symbol catalog upsert ---
                for p in products:
                    pid = p["id"]
                    db_sym = await db.get(Symbol, pid)
                    if db_sym is None:
                        db.add(Symbol(
                            product_id=pid,
                            base_currency=p.get("base_currency", ""),
                            quote_currency=p.get("quote_currency", "USD"),
                            display_name=p.get("display_name", pid),
                            active=1,
                            on_watchlist=1 if pid in watchlist_set else 0,
                        ))
                    else:
                        db_sym.last_seen_at = utcnow_iso()
                        db_sym.active = 1

                # --- BTC market-state gate for macro beta protection ---
                btc_beta_state = "RANGING"
                btc_1h = candles_1h_map.get("BTC-USD")
                if btc_1h and len(btc_1h) >= 20:
                    b_closes = [float(c[4]) for c in btc_1h if len(c) >= 5]
                    if len(b_closes) >= 20:
                        sma_20 = sum(b_closes[-21:-1]) / 20.0
                        if b_closes[-1] < sma_20 and (btc_day_change or 0.0) < -1.5:
                            btc_beta_state = "DUMPING"
                        elif b_closes[-1] > sma_20 and (btc_day_change or 0.0) > 1.5:
                            btc_beta_state = "PUMPING"

                for pid in product_ids:
                    if pid in stale_symbols:
                        db.add(Snapshot(product_id=pid, scan_run_id=scan_run_id, is_stale=1))
                        continue

                    st = stats_map[pid]
                    c1h = candles_1h_map.get(pid)
                    c1d = candles_1d_map.get(pid)
                    c15m = candles_15m_map.get(pid)
                    c4h = candles_4h_map.get(pid)
                    pinned = (pid in watchlist_set)

                    feats = compute_features(
                        raw_stats=st,
                        raw_ticker=st,
                        raw_candles_1h=c1h,
                        raw_candles_1d=c1d,
                        btc_day_change_pct=btc_day_change,
                        raw_candles_15m=c15m,
                        raw_candles_4h=c4h,
                    )
                    feats["product_id"] = pid

                    # Score both directions, then pick the better with a trend constraint
                    long_score = score(feats, cfg.scoring, trade_direction="LONG", regime=current_regime)
                    short_score = score(feats, cfg.scoring, trade_direction="SHORT", regime=current_regime)

                    day_chg = float(feats.get("day_change_pct") or 0.0)
                    is_short_allowed = True
                    if day_chg > 3.0 and (short_score["clamped"] - long_score["clamped"]) < 20.0:
                        is_short_allowed = False

                    if is_short_allowed and short_score["clamped"] > long_score["clamped"]:
                        trade_direction = "SHORT"
                        score_dict = short_score
                    else:
                        trade_direction = "LONG"
                        score_dict = long_score

                    comp_score = score_dict["clamped"]

                    # --- L2 validation (WS cache first, REST fallback) ---
                    if comp_score >= 50.0 or pinned:
                        if pid not in ws_memory._active_symbols:
                            asyncio.create_task(ws_memory.subscribe([pid]))
                        try:
                            l2 = ws_memory.get_l2(pid)
                            if not l2 or not l2.get("bids"):
                                l2 = await adapter.get_l2_snapshot(pid)

                            last_p = float(feats["last_price"])
                            bids = l2.get("bids", [])
                            asks = l2.get("asks", [])

                            feats["l2_buy_vol_2pct"] = sum(
                                float(b[1]) * float(b[0]) for b in bids if float(b[0]) >= last_p * 0.98
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

                            score_dict = score(feats, cfg.scoring, trade_direction=trade_direction, regime=current_regime)
                            comp_score = score_dict["clamped"]
                        except Exception as exc:
                            logger.warning("L2 validation failed for %s: %s", pid, exc)

                    primary_label = label(
                        feats, comp_score, cfg.labeling,
                        trade_direction=trade_direction,
                        regime=current_regime,
                        btc_beta_state=btc_beta_state,
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
                    )

                    # Post-ladder validation: ENTRY_ZONE iff price sits within 0.75% of tranche A
                    if ladder_dict and primary_label not in ("SKIP", "CHASE"):
                        t_a = ladder_dict.get("tranche_a_price")
                        last_p = feats.get("last_price")
                        if t_a and last_p:
                            if abs(float(last_p) - float(t_a)) / float(t_a) <= 0.0075:
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

                    # --- Persist rows ---
                    db.add(Snapshot(
                        product_id=pid,
                        scan_run_id=scan_run_id,
                        raw_stats=json.dumps(st),
                        raw_ticker=json.dumps(st),
                        raw_candles_1h=json.dumps(c1h) if c1h else None,
                        raw_candles_1d=json.dumps(c1d) if c1d else None,
                        is_stale=0,
                    ))

                    db.add(Feature(
                        product_id=pid,
                        scan_run_id=scan_run_id,
                        last_price=feats["last_price"],
                        day_open=feats["day_open"],
                        day_high=feats["day_high"],
                        day_low=feats["day_low"],
                        day_change_pct=feats["day_change_pct"],
                        pos_in_range=feats["pos_in_range"],
                        quote_vol_24h=feats["quote_vol_24h"],
                        vwap_24h=feats["vwap_24h"],
                        rsi_1h=feats["rsi_1h"],
                        rs_vs_btc=feats["rs_vs_btc"],
                        fib_236=feats["fib_236"],
                        fib_382=feats["fib_382"],
                        fib_500=feats["fib_500"],
                        fib_618=feats["fib_618"],
                        fib_786=feats["fib_786"],
                        swing_shelf_7d=feats["swing_shelf_7d"],
                        swing_high_7d=feats["swing_high_7d"],
                        vol_7d_avg_usd=feats["vol_7d_avg_usd"],
                    ))

                    db.add(Score(
                        product_id=pid,
                        scan_run_id=scan_run_id,
                        trade_direction=trade_direction,
                        composite_score=comp_score,
                        label=primary_label,
                        score_breakdown=json.dumps(score_dict),
                    ))

                    if ladder_dict:
                        db.add(Ladder(
                            product_id=pid,
                            scan_run_id=scan_run_id,
                            trade_direction=trade_direction,
                            tranche_a_price=ladder_dict["tranche_a_price"],
                            tranche_b_price=ladder_dict["tranche_b_price"],
                            stop_price=ladder_dict["stop_price"],
                            target_1_price=ladder_dict["target_1_price"],
                            target_2_price=ladder_dict["target_2_price"],
                            tranche_a_size_pct=ladder_dict["tranche_a_size_pct"],
                            tranche_b_size_pct=ladder_dict["tranche_b_size_pct"],
                            basis=json.dumps(ladder_dict["basis"]),
                        ))

                    candidates_out.append({
                        "product_id": pid,
                        "last_price": feats["last_price"],
                        "day_change_pct": feats["day_change_pct"],
                        "pos_in_range": feats["pos_in_range"],
                        "quote_vol_24h": feats["quote_vol_24h"],
                        "composite_score": comp_score,
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
                            ))
                            telegram_alerts.append({
                                "symbol": pid,
                                "score": comp_score,
                                "label": primary_label,
                                "entry": san["tranche_a_price"],
                                "tp": san["target_1_price"],
                                "sl": san["stop_price"],
                            })

                # === THE FIX: commit the scan results ===
                # Without this the AsyncSession closes and rolls back every
                # feature/score/ladder/snapshot added above.
                await db.commit()

                duration = round(time.monotonic() - start_time, 2)
                db_run = await db.get(ScanRun, scan_run_id)
                if db_run:
                    db_run.status = "DONE"
                    db_run.completed_at = utcnow_iso()
                    db_run.duration_seconds = duration
                    db_run.symbols_fetched = len(product_ids)
                    db_run.symbols_stale = len(stale_symbols)
                    db_run.candidates_count = len(candidates_out)
                    await db.commit()

        # Signals + alerts outside the ORM transaction (own connections)
        await _persist_pending_signals(pending_signals)

        for alert in telegram_alerts:
            try:
                from tpt.alerts.telegram import send_setup_alert
                await send_setup_alert(**alert)
            except Exception as exc:
                logger.warning("Telegram alert failed for %s: %s", alert["symbol"], exc)

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
