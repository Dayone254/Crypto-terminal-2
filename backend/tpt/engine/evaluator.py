"""
Forward-testing evaluator daemon.

Three-phase trade lifecycle per signal:
  Phase 1 — WAITING FOR FILL:
      Walks candles from the signal timestamp looking for the first candle
      whose Low <= entry_price.  Until that candle is found the trade is
      considered *unfilled* and neither TP nor SL can be triggered.

  Phase 2 — TRADE ACTIVE (filled, hunting TP/SL):
      Once filled, continues walking subsequent candles.
      • candle.High >= tp_price  →  WIN   (closed_at = that candle's time)
      • candle.Low  <= sl_price  →  LOSS  (closed_at = that candle's time)
      MFE/MAE are only measured from the fill candle onward.

  Phase 3 — CLOSED (WIN or LOSS):
      Row updated in DB; deduplication guard cleared for next signal.

If Coinbase returns fewer than 300 candles and neither TP/SL has hit,
the trade stays PENDING and the evaluator retries next cycle.
"""

import asyncio
import logging
from datetime import UTC, datetime

import httpx

from tpt.config.strategy import load_strategy
from tpt.data.database import get_connection

logger = logging.getLogger(__name__)


def break_even_arm_pct(risk_pct: float, be_arm_r: float, fallback_pct: float = 2.5) -> float:
    """The favourable excursion, in percent, at which the stop moves to entry.

    Expressed in R so it scales with the trade's own risk. The previous rule was a
    flat ``mfe >= 2.5`` PERCENT regardless of risk, which on a 5% stop armed at
    0.5R — earlier than the trade's own geometry can survive. All eight
    break-evens in the first 22 closed trades had MFE just over 2.5% and MAE
    under 1.24%: price nudged past the trigger, the stop jumped to entry, and the
    trade drifted back out flat.

    ``fallback_pct`` covers the degenerate case of a signal with no usable risk
    distance, where there is no R to scale by.
    """
    if risk_pct <= 0:
        return fallback_pct
    return be_arm_r * risk_pct

_COINBASE_URL = "https://api.exchange.coinbase.com/products/{symbol}/candles"


async def _fetch_candles(client: httpx.AsyncClient, symbol: str, start_ts: int) -> list:
    """Fetch 15m candles from `start_ts` (unix seconds) for `symbol` with explicit end timestamp and pagination."""
    all_candles = []
    current_start = start_ts
    now_ts = int(datetime.now(UTC).timestamp())
    url = _COINBASE_URL.format(symbol=symbol)

    while current_start < now_ts:
        # Request up to 300 15m candles per chunk (300 * 900 = 270,000s = 75 hours)
        end_ts = min(current_start + (300 * 900), now_ts)
        start_iso = datetime.fromtimestamp(current_start, tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        end_iso = datetime.fromtimestamp(end_ts, tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

        try:
            res = await client.get(url, params={"granularity": 900, "start": start_iso, "end": end_iso}, timeout=10.0)
            if res.status_code != 200:
                break
            data = res.json()
            if not data:
                break
            
            # Coinbase returns newest-first
            sorted_chunk = sorted(data, key=lambda x: x[0])
            all_candles.extend(sorted_chunk)

            last_candle_ts = sorted_chunk[-1][0]
            if len(data) < 300 or last_candle_ts >= end_ts or last_candle_ts <= current_start:
                current_start = end_ts
            else:
                current_start = last_candle_ts + 900 # Next 15m window
        except Exception as exc:
            logger.error("Failed fetching paginated candles for %s: %s", symbol, exc)
            break

    # Deduplicate and strictly filter candles that close after start_ts
    seen_ts = set()
    unique_candles = []
    for c in sorted(all_candles, key=lambda x: x[0]):
        if c[0] + 900 > start_ts and c[0] not in seen_ts:
            seen_ts.add(c[0])
            unique_candles.append(c)

    return unique_candles


async def _fetch_1m_candles(client: httpx.AsyncClient, symbol: str, start_ts: int, end_ts: int) -> list:
    """Fetch 1m sub-candles for interval [start_ts, end_ts] to resolve same-candle TP/SL collisions."""
    url = _COINBASE_URL.format(symbol=symbol)
    start_iso = datetime.fromtimestamp(start_ts, tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    end_iso = datetime.fromtimestamp(end_ts, tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        res = await client.get(url, params={"granularity": 60, "start": start_iso, "end": end_iso}, timeout=10.0)
        if res.status_code == 200:
            data = res.json()
            if isinstance(data, list):
                return sorted(data, key=lambda x: x[0])
    except Exception as exc:
        logger.warning("Failed fetching 1m sub-candles for %s: %s", symbol, exc)
    return []


async def _resolve_same_candle_collision(
    client: httpx.AsyncClient,
    symbol: str,
    c_time: int,
    direction: str,
    eff_tp: float,
    eff_sl: float,
    is_be_active: bool,
    c_open: float,
    c_close: float,
) -> str:
    """Fetch 1m sub-candles for [c_time, c_time + 900] to determine whether TP or SL was touched first."""
    candles_1m = await _fetch_1m_candles(client, symbol, c_time, c_time + 900)
    if candles_1m:
        for m_cand in candles_1m:
            _, m_low, m_high, _, _, *_ = m_cand
            if direction == "LONG":
                hit_tp_1m = m_high >= eff_tp
                hit_sl_1m = m_low <= eff_sl
                if hit_tp_1m and not hit_sl_1m:
                    return "WIN"
                elif hit_sl_1m and not hit_tp_1m:
                    return "BREAK_EVEN" if is_be_active else "LOSS"
            else:  # SHORT
                hit_tp_1m = m_low <= eff_tp
                hit_sl_1m = m_high >= eff_sl
                if hit_tp_1m and not hit_sl_1m:
                    return "WIN"
                elif hit_sl_1m and not hit_tp_1m:
                    return "BREAK_EVEN" if is_be_active else "LOSS"

    # Fallback to directional candle body color heuristic
    if direction == "LONG":
        return "WIN" if c_open <= c_close else ("BREAK_EVEN" if is_be_active else "LOSS")
    else:
        return "WIN" if c_open >= c_close else ("BREAK_EVEN" if is_be_active else "LOSS")


async def process_signals():
    """Evaluate all PENDING signals against real price action."""
    async with get_connection() as conn, conn.execute(
        "SELECT * FROM signals WHERE status='PENDING'"
    ) as cur:
        signals = await cur.fetchall()

    if not signals:
        return

    # Read once per pass rather than per signal: strategy.yaml is hot-reloaded, and
    # the exit geometry should follow the same config the ladder used to place the
    # trade. Falls back to the default rather than failing the whole pass.
    try:
        be_arm_r = load_strategy().ladder.be_arm_r
    except Exception:
        be_arm_r = 1.0

    updates = []

    async with httpx.AsyncClient() as client:
        for sig in signals:
            sig = dict(sig)
            try:
                sig_time = sig["timestamp"]
                
                # Fix 4: Order expiry filter
                try:
                    expiry_hrs = load_strategy().ladder.order_expiry_hours
                except Exception:
                    expiry_hrs = 6
                
                now_ts = int(datetime.now(UTC).timestamp())
                if not sig.get("filled_at") and (now_ts - sig_time > (expiry_hrs * 3600)):
                    updates.append((
                        "EXPIRED", float(sig["mfe"] or 0.0), float(sig["mae"] or 0.0), 
                        now_ts, None, None, None, None, "EXPIRED", sig.get("trail_sl"), sig["id"]
                    ))
                    continue

                # Use fill time as fetch start if already filled, else signal time
                fetch_from = sig.get("filled_at") or sig_time
                candles = await _fetch_candles(client, sig["symbol"], fetch_from)
                if not candles:
                    continue

                already_filled = bool(sig.get("filled_at"))
                fill_price = sig.get("fill_price")

                status = sig.get("status") or "PENDING"
                mfe = float(sig["mfe"] or 0.0)
                mae = float(sig["mae"] or 0.0)
                filled_at = sig.get("filled_at")
                closed_at = sig.get("closed_at")
                partial_exit_at = sig.get("partial_exit_at")
                partial_exit_price = sig.get("partial_exit_price")
                final_status = sig.get("final_status")
                current_trail_sl = sig.get("trail_sl")

                # Infer trade direction if not set
                direction = sig.get("trade_direction") or ("SHORT" if sig["sl_price"] > sig["entry_price"] else "LONG")

                for i, c in enumerate(candles):
                    c_time, c_low, c_high, c_open, c_close, *_ = c

                    # ── STRICT TIMESTAMP GUARD: NEVER evaluate candles that closed BEFORE signal creation time ──
                    if c_time + 900 <= sig_time:
                        continue
                        
                    # Compute live 14-period ATR for Chandelier Exits
                    live_atr = abs(sig["entry_price"] - sig["sl_price"]) # strict fallback
                    if i >= 14:
                        trs = []
                        for j in range(i-13, i+1):
                            prev_c = float(candles[j-1][4])
                            h = float(candles[j][2])
                            lo = float(candles[j][1])
                            trs.append(max(h - lo, abs(h - prev_c), abs(lo - prev_c)))
                        live_atr = sum(trs) / len(trs)

                    # ── Phase 1: Wait for entry fill ──────────────────────
                    if not already_filled:
                        if direction == "LONG" and c_low <= sig["entry_price"]:
                            already_filled = True
                            filled_at = c_time
                            fill_price = min(c_open, sig["entry_price"])
                            logger.info("Signal %d (%s LONG) FILLED at %s on candle %s", sig["id"], sig["symbol"], fill_price, c_time)
                        elif direction == "SHORT" and c_high >= sig["entry_price"]:
                            already_filled = True
                            filled_at = c_time
                            fill_price = max(c_open, sig["entry_price"])
                            logger.info("Signal %d (%s SHORT) FILLED at %s on candle %s", sig["id"], sig["symbol"], fill_price, c_time)
                        else:
                            # Not filled yet — skip TP/SL check
                            continue

                    # ── Phase 2: Trade active — calculate fill-anchored SL/TP, track MFE/MAE, hunt TP/SL ─
                    if fill_price and fill_price > 0 and not closed_at:
                        # Anchor risk and reward deltas to actual fill price
                        entry_p = sig["entry_price"] if sig["entry_price"] > 0 else fill_price
                        risk_delta = abs(entry_p - sig["sl_price"])
                        tp_delta = abs(sig["tp_price"] - entry_p)

                        tp2_p = sig.get("tp2_price")
                        if tp2_p is None or tp2_p <= 0.0:
                            tp2_p = sig["tp_price"] + (2.0 * risk_delta) if direction == "LONG" else sig["tp_price"] - (2.0 * risk_delta)
                        tp2_delta = abs(tp2_p - entry_p)

                        if direction == "LONG":
                            eff_sl = fill_price - risk_delta
                            eff_tp = fill_price + tp_delta
                            eff_tp2 = fill_price + tp2_delta
                            mfe_cand = (c_high - fill_price) / fill_price * 100
                            mae_cand = (c_low  - fill_price) / fill_price * 100
                        else: # SHORT
                            eff_sl = fill_price + risk_delta
                            eff_tp = fill_price - tp_delta
                            eff_tp2 = fill_price - tp2_delta
                            mfe_cand = (fill_price - c_low) / fill_price * 100
                            mae_cand = (fill_price - c_high) / fill_price * 100

                        mfe = max(mfe, mfe_cand)
                        mae = min(mae, mae_cand)

                        # ── BREAK-EVEN TRAILING STOP (Pre-T1) ──
                        # Armed when the trade has earned its own risk back, in R —
                        # see break_even_arm_pct for why this is not a flat percent.
                        risk_pct = (risk_delta / entry_p * 100.0) if entry_p > 0 else 0.0
                        be_arm_pct = break_even_arm_pct(risk_pct, be_arm_r)
                        is_be_active = mfe >= be_arm_pct
                        if is_be_active and not partial_exit_at:
                            if direction == "LONG":
                                eff_sl = max(eff_sl, fill_price)
                            else:
                                eff_sl = min(eff_sl, fill_price)

                        # ── T2 HUNTING (Partial Exit complete) ─────────
                        if partial_exit_at:
                            if direction == "LONG":
                                max_seen_price = fill_price + (mfe / 100.0 * fill_price)
                                trail_sl = max(fill_price, max_seen_price - (3.0 * live_atr))
                                current_trail_sl = trail_sl
                                
                                hit_tp2 = c_high >= eff_tp2
                                hit_sl = c_low <= trail_sl
                                
                                if hit_tp2 and hit_sl:
                                    res = await _resolve_same_candle_collision(client, sig["symbol"], c_time, direction, eff_tp2, trail_sl, True, c_open, c_close)
                                    status = final_status = res
                                    closed_at = c_time
                                    break
                                elif hit_tp2:
                                    status = final_status = "WIN"
                                    closed_at = c_time
                                    break
                                elif hit_sl:
                                    status = final_status = "PARTIAL_WIN"
                                    closed_at = c_time
                                    break
                            else:
                                min_seen_price = fill_price - (mfe / 100.0 * fill_price)
                                trail_sl = min(fill_price, min_seen_price + (3.0 * live_atr))
                                current_trail_sl = trail_sl
                                
                                hit_tp2 = c_low <= eff_tp2
                                hit_sl = c_high >= trail_sl
                                
                                if hit_tp2 and hit_sl:
                                    res = await _resolve_same_candle_collision(client, sig["symbol"], c_time, direction, eff_tp2, trail_sl, True, c_open, c_close)
                                    status = final_status = res
                                    closed_at = c_time
                                    break
                                elif hit_tp2:
                                    status = final_status = "WIN"
                                    closed_at = c_time
                                    break
                                elif hit_sl:
                                    status = final_status = "PARTIAL_WIN"
                                    closed_at = c_time
                                    break
                                    
                        # ── T1 HUNTING (No Partial Exit yet) ─────────
                        else:
                            if direction == "LONG":
                                hit_tp = c_high >= eff_tp
                                hit_sl = c_low <= eff_sl
                                if hit_tp and hit_sl:
                                    res = await _resolve_same_candle_collision(client, sig["symbol"], c_time, direction, eff_tp, eff_sl, is_be_active, c_open, c_close)
                                    if res == "WIN":
                                        partial_exit_at = c_time
                                        partial_exit_price = eff_tp
                                        status = "ACTIVE_T2"
                                    else:
                                        status = final_status = res
                                        closed_at = c_time
                                        break
                                elif hit_tp:
                                    partial_exit_at = c_time
                                    partial_exit_price = eff_tp
                                    status = "ACTIVE_T2"
                                elif hit_sl:
                                    status = final_status = "BREAK_EVEN" if is_be_active else "LOSS"
                                    closed_at = c_time
                                    break
                            else:
                                hit_tp = c_low <= eff_tp
                                hit_sl = c_high >= eff_sl
                                if hit_tp and hit_sl:
                                    res = await _resolve_same_candle_collision(client, sig["symbol"], c_time, direction, eff_tp, eff_sl, is_be_active, c_open, c_close)
                                    if res == "WIN":
                                        partial_exit_at = c_time
                                        partial_exit_price = eff_tp
                                        status = "ACTIVE_T2"
                                    else:
                                        status = final_status = res
                                        closed_at = c_time
                                        break
                                elif hit_tp:
                                    partial_exit_at = c_time
                                    partial_exit_price = eff_tp
                                    status = "ACTIVE_T2"
                                elif hit_sl:
                                    status = final_status = "BREAK_EVEN" if is_be_active else "LOSS"
                                    closed_at = c_time
                                    break

                # Collect update once per signal — AFTER the candle loop completes (not inside it)
                updates.append((status, mfe, mae, closed_at, filled_at, fill_price, partial_exit_at, partial_exit_price, final_status, current_trail_sl, sig["id"]))
            except Exception as exc:
                logger.error("Error evaluating signal %d: %s", sig.get("id"), exc)
                    
    # Execute all updates in a single transaction, serialized against the
    # scanner and API writers (SQLite permits one writer at a time).
    if updates:
        from tpt.db.write_lock import db_write_lock
        async with db_write_lock, get_connection() as conn:
            await conn.executemany(
                """UPDATE signals
                       SET status=?, mfe=?, mae=?, closed_at=?,
                           filled_at=?, fill_price=?,
                           partial_exit_at=?, partial_exit_price=?, final_status=?, trail_sl=?
                       WHERE id=?""",
                updates
            )
            await conn.commit()


async def evaluator_loop():
    """Background daemon — runs process_signals every 2 minutes."""
    logger.info("Backtest Evaluator Engine started.")
    while True:
        try:
            await process_signals()
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.error("Evaluator loop exception: %s", exc)
        await asyncio.sleep(120)
