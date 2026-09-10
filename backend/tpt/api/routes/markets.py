"""Markets API routes — fetch latest symbol setup quality, features, and limit ladders."""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException, status

from tpt.db.connection import AsyncSessionLocal
from tpt.db.queries import get_latest_ladder_and_score
from tpt.engine.ladder import format_ladder_text, sanitize_ladder_dict

router = APIRouter()


@router.get("/markets", response_model=list[dict[str, Any]])
async def list_markets() -> list[dict[str, Any]]:
    """Return all candidates from the most recent scan run that produced data."""
    from sqlalchemy import func, select

    from tpt.db.models import Feature, Ladder, ScanRun, Score, Symbol

    async with AsyncSessionLocal() as db:
        # Pick the newest finished run that actually has scores. Filtering on
        # `status == "DONE"` alone hid every scan whose final status write
        # failed, leaving the dashboard stuck on stale or empty data.
        recent_res = await db.execute(
            select(ScanRun)
            .where(ScanRun.status != "RUNNING")
            .order_by(ScanRun.started_at.desc())
            .limit(25)
        )
        latest_scan = None
        for candidate_run in recent_res.scalars().all():
            score_count = await db.execute(
                select(func.count()).select_from(Score).where(Score.scan_run_id == candidate_run.id)
            )
            if score_count.scalar_one() > 0:
                latest_scan = candidate_run
                break

        if not latest_scan:
            return []

        # Query scores, features, ladders, symbols for latest scan run
        stmt = (
            select(Score, Feature, Ladder, Symbol)
            .join(Feature, (Score.product_id == Feature.product_id) & (Score.scan_run_id == Feature.scan_run_id))
            .outerjoin(Ladder, (Score.product_id == Ladder.product_id) & (Score.scan_run_id == Ladder.scan_run_id))
            .outerjoin(Symbol, Score.product_id == Symbol.product_id)
            .where(Score.scan_run_id == latest_scan.id)
            .order_by(Score.composite_score.desc())
        )
        res = await db.execute(stmt)
        rows = res.all()

        results = []
        for score_rec, feat_rec, lad_rec, sym_rec in rows:
            ladder_dict = None
            if lad_rec:
                ladder_dict = sanitize_ladder_dict({
                    "tranche_a_price":    lad_rec.tranche_a_price,
                    "tranche_b_price":    lad_rec.tranche_b_price,
                    "stop_price":         lad_rec.stop_price,
                    "target_1_price":     lad_rec.target_1_price,
                    "target_2_price":     lad_rec.target_2_price,
                    "tranche_a_size_pct": lad_rec.tranche_a_size_pct,
                    "tranche_b_size_pct": lad_rec.tranche_b_size_pct,
                    "trade_direction":    score_rec.trade_direction,
                })
            
            score_breakdown = json.loads(score_rec.score_breakdown) if score_rec.score_breakdown else {}
            tags = score_breakdown.get("tags", [])

            results.append({
                "product_id": score_rec.product_id,
                "last_price": feat_rec.last_price,
                "day_change_pct": feat_rec.day_change_pct,
                "composite_score": score_rec.composite_score,
                "trade_direction": getattr(score_rec, "trade_direction", "LONG"),
                "label": score_rec.label,
                "pos_in_range": feat_rec.pos_in_range,
                "quote_vol_24h": feat_rec.quote_vol_24h,
                "ladder": ladder_dict,
                "tags": tags,
                "pinned": bool(sym_rec and sym_rec.on_watchlist),
            })

        return results


@router.get("/markets/{product_id}", response_model=dict[str, Any])
async def get_market_detail(product_id: str) -> dict[str, Any]:
    """Return latest setup quality, score, label, and ladder for a given symbol."""
    async with AsyncSessionLocal() as db:
        data = await get_latest_ladder_and_score(db, product_id.upper())
        if not data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No scan data found for symbol '{product_id.upper()}'",
            )
            
        # Dynamically append macro Gamma mapping (Binance eAPI)
        from tpt.engine.options_flow import calculate_macro_gamma_exposure
        underlying = product_id.split("-")[0].upper()
        spot = float(data.get("last_price", 0.0))
        
        # Note: During high volatility, extracting the entire chain may take 1-2s. 
        gamma_data = await calculate_macro_gamma_exposure(underlying, spot)
            
        data["options_flow"] = gamma_data
        
        return data


@router.get("/markets/{product_id}/candles", response_model=list[list[Any]])
async def get_market_candles(product_id: str, granularity: int = 3600) -> list[list[Any]]:
    """Proxy candle requests through backend to avoid CORS and ensure valid user-agent.
    
    Supports Coinbase as primary and Binance Futures API as fallback.
    """
    from tpt.adapters.binance_futures import get_futures_klines
    from tpt.adapters.coinbase import CoinbaseAdapter

    adapter = CoinbaseAdapter()
    data = []
    try:
        data = await adapter.get_candles(product_id.upper(), granularity, limit=300)
    except Exception:
        data = []
    finally:
        await adapter.close()

    # Fallback to Binance Futures API if Coinbase returned empty
    if not data:
        tf_map = {900: "15m", 3600: "1h", 21600: "6h", 86400: "1d"}
        interval = tf_map.get(granularity, "1h")
        data = await get_futures_klines(product_id.upper(), interval=interval, limit=300)

    return data if data else []


@router.get("/markets/{product_id}/ladder", response_model=dict[str, Any])
async def get_market_ladder_drawer(product_id: str) -> dict[str, Any]:
    """Return candidate drawer payload including PRD §8 copyable text template."""
    async with AsyncSessionLocal() as db:
        data = await get_latest_ladder_and_score(db, product_id.upper())
        if not data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No scan data found for symbol '{product_id.upper()}'",
            )

        ladder = data.get("ladder")
        copy_text = None
        if ladder:
            copy_text = format_ladder_text(
                product_id=data["product_id"],
                score_val=data["composite_score"],
                lbl=data["label"],
                ladder=ladder,
            )

        from tpt.engine.options_flow import calculate_macro_gamma_exposure
        underlying = product_id.split("-")[0].upper()
        spot = float(data.get("last_price", 0.0))
        gamma_data = await calculate_macro_gamma_exposure(underlying, spot)

        return {
            "product_id": data["product_id"],
            "composite_score": data["composite_score"],
            "label": data["label"],
            "ladder": ladder,
            "copy_text": copy_text,
            "updated_at": data["updated_at"],
            "options_flow": gamma_data
        }


@router.get("/markets/{product_id}/trades/history", response_model=list[dict[str, Any]])
async def get_market_trade_history(product_id: str) -> list[dict[str, Any]]:
    """Return distinct historical scan/trade ladders for a given symbol, deduplicated by time & price."""
    from datetime import datetime

    from sqlalchemy import select

    from tpt.db.models import Ladder, Score

    async with AsyncSessionLocal() as db:
        stmt = (
            select(Score, Ladder)
            .join(Ladder, (Score.product_id == Ladder.product_id) & (Score.scan_run_id == Ladder.scan_run_id))
            .where(Score.product_id == product_id.upper())
            .order_by(Score.computed_at.asc())  # ASC so dedup pointer advances forward in time
            .limit(100)
        )
        res = await db.execute(stmt)
        rows = res.all()

        history = []
        last_added_time: datetime | None = None
        last_added_price: float | None = None

        for score_rec, lad_rec in rows:
            dt = datetime.fromisoformat(score_rec.computed_at) if isinstance(score_rec.computed_at, str) else score_rec.computed_at
            price = lad_rec.tranche_a_price

            # Deduplication: Skip if setup occurred within 4 hours AND price is within 2% of previous setup
            if last_added_time and last_added_price and price and price > 0:
                time_diff = abs((last_added_time - dt).total_seconds())
                price_diff_pct = abs((price - last_added_price) / last_added_price) * 100.0

                if time_diff < 14400 and price_diff_pct < 2.0:
                    continue  # Skip duplicate scan entry

            raw_hist = {
                "tranche_a_price": lad_rec.tranche_a_price,
                "tranche_b_price": lad_rec.tranche_b_price,
                "stop_price": lad_rec.stop_price,
                "target_1_price": lad_rec.target_1_price,
                "target_2_price": lad_rec.target_2_price,
            }
            sanitized = sanitize_ladder_dict(raw_hist) or raw_hist

            history.append({
                "computed_at": score_rec.computed_at,
                "trade_direction": getattr(score_rec, "trade_direction", "LONG"),
                "composite_score": score_rec.composite_score,
                "label": score_rec.label,
                "tranche_a_price": sanitized["tranche_a_price"],
                "tranche_b_price": sanitized["tranche_b_price"],
                "stop_price": sanitized["stop_price"],
                "target_1_price": sanitized["target_1_price"],
                "target_2_price": sanitized["target_2_price"],
            })

            last_added_time = dt
            last_added_price = price

        return history
