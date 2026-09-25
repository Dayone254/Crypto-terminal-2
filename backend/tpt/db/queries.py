"""Database query helpers for symbols, watchlist, ladders, and watches."""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tpt.db.models import Feature, Ladder, Score, Symbol
from tpt.engine.ladder import sanitize_ladder_dict


async def add_to_watchlist(db: AsyncSession, product_id: str) -> Symbol:
    """Pin a symbol to the watchlist."""
    sym = await db.get(Symbol, product_id)
    if sym is None:
        parts = product_id.split("-")
        base = parts[0] if len(parts) > 0 else product_id
        quote = parts[1] if len(parts) > 1 else "USD"
        sym = Symbol(
            product_id=product_id,
            base_currency=base,
            quote_currency=quote,
            display_name=product_id,
            on_watchlist=1,
            active=1,
        )
        db.add(sym)
    else:
        sym.on_watchlist = 1
    await db.commit()
    await db.refresh(sym)
    return sym


async def remove_from_watchlist(db: AsyncSession, product_id: str) -> bool:
    """Unpin a symbol from the watchlist."""
    sym = await db.get(Symbol, product_id)
    if sym is None:
        return False
    sym.on_watchlist = 0
    await db.commit()
    return True


async def get_watchlist(db: AsyncSession) -> list[Symbol]:
    """Get all pinned watchlist symbols."""
    res = await db.execute(select(Symbol).where(Symbol.on_watchlist == 1).order_by(Symbol.product_id))
    return list(res.scalars().all())


async def get_latest_ladder_and_score(
    db: AsyncSession, product_id: str
) -> dict[str, Any] | None:
    """Fetch the latest score, label, feature metrics, and ladder for a given symbol."""
    stmt = (
        select(Score, Ladder, Feature)
        .outerjoin(Ladder, (Score.product_id == Ladder.product_id) & (Score.scan_run_id == Ladder.scan_run_id))
        .outerjoin(Feature, (Score.product_id == Feature.product_id) & (Score.scan_run_id == Feature.scan_run_id))
        .where(Score.product_id == product_id)
        .order_by(Score.scan_run_id.desc())
        .limit(1)
    )
    res = await db.execute(stmt)
    row = res.first()
    if row is None:
        return None

    score_rec, ladder_rec, feat_rec = row

    ladder_dict: dict[str, Any] | None = None
    if ladder_rec:
        ladder_dict = {
            "tranche_a_price": ladder_rec.tranche_a_price,
            "tranche_b_price": ladder_rec.tranche_b_price,
            "stop_price": ladder_rec.stop_price,
            "target_1_price": ladder_rec.target_1_price,
            "target_2_price": ladder_rec.target_2_price,
            "tranche_a_size_pct": ladder_rec.tranche_a_size_pct,
            "tranche_b_size_pct": ladder_rec.tranche_b_size_pct,
            "trade_direction": getattr(ladder_rec, "trade_direction", "LONG"),
            "basis": json.loads(ladder_rec.basis) if ladder_rec.basis else {},
            # Carried through so sanitize honours the calibrated multiple rather
            # than restoring its 2.0R default on every read.
            "target_r": getattr(ladder_rec, "target_r", None),
        }
        ladder_dict = sanitize_ladder_dict(ladder_dict)

    feat_dict: dict[str, Any] | None = None
    if feat_rec:
        feat_dict = {
            "last_price": feat_rec.last_price,
            "vwap_24h": feat_rec.vwap_24h,
            "fib_236": feat_rec.fib_236,
            "fib_382": feat_rec.fib_382,
            "fib_500": feat_rec.fib_500,
            "fib_618": feat_rec.fib_618,
            "fib_786": feat_rec.fib_786,
            "swing_shelf_7d": feat_rec.swing_shelf_7d,
            "swing_high_7d": feat_rec.swing_high_7d,
        }

    # The raw readings the scorer actually consumed, straight out of the flight
    # recorder. `score_breakdown` carries the *normalised* components (all in
    # [-1, 1]); prose needs the raw values to say "RSI 42" instead of
    # "momentum +0.32" — and without them the UI could only assert, not report.
    # Null for rows written before the recorder existed.
    inputs: dict[str, Any] | None = None
    raw_vector = getattr(feat_rec, "feature_vector", None) if feat_rec else None
    if raw_vector:
        try:
            parsed = json.loads(raw_vector)
            if isinstance(parsed, dict):
                inputs = parsed
        except (TypeError, ValueError):
            inputs = None

    # Derive trade_direction mathematically from ladder if present
    effective_direction = getattr(score_rec, "trade_direction", None)
    if ladder_rec and ladder_rec.stop_price and ladder_rec.tranche_a_price:
        if ladder_rec.stop_price > ladder_rec.tranche_a_price:
            effective_direction = "SHORT"
        elif ladder_rec.stop_price < ladder_rec.tranche_a_price:
            effective_direction = "LONG"

    if not effective_direction:
        effective_direction = "LONG"

    if ladder_dict:
        ladder_dict["trade_direction"] = effective_direction

    return {
        "product_id": product_id,
        "composite_score": score_rec.composite_score,
        # Belief state: how good the evidence was, and how much of the model it
        # covered — so a bare score can never be read as high conviction on its own.
        "edge": getattr(score_rec, "edge", None),
        "coverage": getattr(score_rec, "coverage", None),
        "coverage_band": getattr(score_rec, "coverage_band", None),
        "label": score_rec.label,
        "trade_direction": effective_direction,
        "last_price": feat_rec.last_price if feat_rec else None,
        "score_breakdown": json.loads(score_rec.score_breakdown) if score_rec.score_breakdown else {},
        "ladder": ladder_dict,
        "features": feat_dict,
        "inputs": inputs,
        "updated_at": score_rec.computed_at,
    }
