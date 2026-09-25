"""Research pipeline routes — walk-forward backtests, candidates, shadow mode, and promotion governance."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel, Field

from tpt.backtest.data_fetcher import expand_universe_history
from tpt.backtest.shadow import (
    list_staged_shadow_pipelines,
    promote_shadow_pipeline_manual,
    stage_candidate_strategy,
)
from tpt.backtest.storage import (
    SURVIVORSHIP_BIAS_NOTE,
    get_symbol_listing_bounds_sync,
    load_historical_candles_sync,
)
from tpt.backtest.walk_forward import StrategyCandidateConfig, run_walk_forward_backtest
from tpt.config.settings import settings

router = APIRouter()
logger = logging.getLogger(__name__)


class ExpandHistoryRequest(BaseModel):
    symbols: list[str] = Field(default_factory=lambda: ["BTC-USD", "ETH-USD", "SOL-USD", "AVAX-USD", "LINK-USD"])
    years: float = Field(default=20.0, ge=0.5, le=20.0)


class StageCandidateRequest(BaseModel):
    candidate_name: str
    min_composite_score: float = 60.0
    min_quote_volume: float = 1_000_000.0
    atr_stop_mult: float = 1.5


class PromoteRequest(BaseModel):
    pipeline_version: str
    confirm: bool = Field(..., description="Must explicitly confirm manual promotion")


@router.get("/summary")
async def research_summary():
    """Summary of historical dataset bounds, staged shadow pipelines, and methodological notes."""
    bounds = await asyncio.to_thread(get_symbol_listing_bounds_sync)
    shadow_pipelines = await asyncio.to_thread(list_staged_shadow_pipelines)

    total_candles = sum(b["total_candles"] for b in bounds.values())
    return {
        "historical_symbols_count": len(bounds),
        "total_candles_stored": total_candles,
        "symbol_listing_bounds": bounds,
        "staged_shadow_pipelines": shadow_pipelines,
        "min_shadow_sample_size": settings.min_shadow_sample_size,
        "survivorship_bias_note": SURVIVORSHIP_BIAS_NOTE,
    }


@router.post("/expand-history")
async def expand_history_endpoint(req: ExpandHistoryRequest):
    """Trigger historical data expansion for up to 5 years per symbol."""
    try:
        res = await expand_universe_history(req.symbols, granularity=3600, years=req.years)
        return res
    except Exception as exc:
        logger.error("Expand history failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


from tpt.strategies.registry import get_all_strategies, get_strategy_by_id

@router.get("/strategies")
async def list_available_strategies():
    """List all available pluggable strategy plugins in tpt/strategies/."""
    strategies = await asyncio.to_thread(get_all_strategies)
    return {
        "strategies": [st.to_dict() for st in strategies],
        "count": len(strategies),
    }


from dataclasses import asdict

@router.post("/run-backtest")
async def run_backtest_endpoint(
    background_tasks: BackgroundTasks,
    symbols: list[str] = Query(default=["BTC-USD", "ETH-USD", "SOL-USD"]),
    strategy_id: str | None = Query(default=None),
):
    """Run walk-forward backtest evaluation across strategy candidates or specific strategy plugin."""
    try:
        candidates = [
            StrategyCandidateConfig(name="Default v2.0 (Score >= 60)", min_composite_score=60.0),
            StrategyCandidateConfig(name="Conservative (Score >= 70)", min_composite_score=70.0),
            StrategyCandidateConfig(name="Aggressive (Score >= 55)", min_composite_score=55.0),
            StrategyCandidateConfig(name="High Volume Floor ($2M+)", min_composite_score=60.0, min_quote_volume=2_000_000.0),
        ]
        
        plugins = None
        if strategy_id:
            st = get_strategy_by_id(strategy_id)
            if st:
                plugins = [st]
                candidates = None
        else:
            plugins = get_all_strategies()

        # Detach the heavy run into a background task to survive the 60s global timeout
        background_tasks.add_task(run_walk_forward_backtest, symbols, candidates=candidates, strategies=plugins)
        
        return {
            "status": "QUEUED", 
            "message": "Long-running walk forward evaluation shifted to background.",
            "symbols_queued": symbols,
            "survivorship_bias_note": SURVIVORSHIP_BIAS_NOTE,
        }
    except Exception as exc:
        logger.error("Run backtest failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/shadow")
async def list_shadow_pipelines():
    """List currently staged shadow pipeline versions and promotion eligibility."""
    pipelines = await asyncio.to_thread(list_staged_shadow_pipelines)
    return {
        "pipelines": pipelines,
        "min_shadow_sample_size": settings.min_shadow_sample_size,
    }


@router.post("/shadow/stage")
async def stage_candidate_endpoint(req: StageCandidateRequest):
    """Stage a candidate strategy to run forward in shadow mode."""
    res = await asyncio.to_thread(
        stage_candidate_strategy,
        candidate_name=req.candidate_name,
        config_dict=req.model_dump(),
    )
    return res


@router.post("/shadow/promote")
async def promote_shadow_endpoint(req: PromoteRequest):
    """Manually promote a staged shadow pipeline to live status.
    
    NON-NEGOTIABLE: Requires explicit manual confirmation. Never automated.
    """
    if not req.confirm:
        raise HTTPException(status_code=400, detail="Explicit confirmation boolean required for promotion.")

    try:
        res = await asyncio.to_thread(promote_shadow_pipeline_manual, req.pipeline_version)
        return res
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error("Promotion failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))
