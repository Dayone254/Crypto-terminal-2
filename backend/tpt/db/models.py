"""SQLAlchemy ORM models for all TPT tables."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow_iso() -> str:
    return datetime.now(UTC).isoformat()


def new_uuid() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


class Symbol(Base):
    __tablename__ = "symbols"

    product_id: Mapped[str] = mapped_column(String, primary_key=True)
    base_currency: Mapped[str] = mapped_column(String, nullable=False)
    quote_currency: Mapped[str] = mapped_column(String, nullable=False)
    display_name: Mapped[str | None] = mapped_column(String)
    min_market_funds: Mapped[float | None] = mapped_column(Float)
    active: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    on_watchlist: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    first_seen_at: Mapped[str] = mapped_column(String, nullable=False, default=utcnow_iso)
    last_seen_at: Mapped[str] = mapped_column(String, nullable=False, default=utcnow_iso)


class ScanRun(Base):
    __tablename__ = "scan_runs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_uuid)
    trigger: Mapped[str] = mapped_column(String, nullable=False)  # SCHEDULED | ON_DEMAND
    started_at: Mapped[str] = mapped_column(String, nullable=False, default=utcnow_iso)
    completed_at: Mapped[str | None] = mapped_column(String)
    duration_seconds: Mapped[float | None] = mapped_column(Float)
    symbols_fetched: Mapped[int | None] = mapped_column(Integer)
    symbols_stale: Mapped[int | None] = mapped_column(Integer)
    candidates_count: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String, nullable=False, default="RUNNING")
    error_message: Mapped[str | None] = mapped_column(Text)
    config_snapshot: Mapped[str | None] = mapped_column(Text)  # JSON


class Snapshot(Base):
    __tablename__ = "snapshots"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_uuid)
    product_id: Mapped[str] = mapped_column(String, ForeignKey("symbols.product_id"), nullable=False)
    scan_run_id: Mapped[str] = mapped_column(String, ForeignKey("scan_runs.id"), nullable=False, index=True)
    fetched_at: Mapped[str] = mapped_column(String, nullable=False, default=utcnow_iso)
    raw_stats: Mapped[str | None] = mapped_column(Text)  # JSON
    raw_ticker: Mapped[str | None] = mapped_column(Text)  # JSON
    raw_candles_1h: Mapped[str | None] = mapped_column(Text)  # JSON
    raw_candles_1d: Mapped[str | None] = mapped_column(Text)  # JSON
    is_stale: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class Feature(Base):
    __tablename__ = "features"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_uuid)
    product_id: Mapped[str] = mapped_column(String, ForeignKey("symbols.product_id"), nullable=False, index=True)
    scan_run_id: Mapped[str] = mapped_column(String, ForeignKey("scan_runs.id"), nullable=False, index=True)
    computed_at: Mapped[str] = mapped_column(String, nullable=False, default=utcnow_iso)
    last_price: Mapped[float | None] = mapped_column(Float)
    day_open: Mapped[float | None] = mapped_column(Float)
    day_high: Mapped[float | None] = mapped_column(Float)
    day_low: Mapped[float | None] = mapped_column(Float)
    day_change_pct: Mapped[float | None] = mapped_column(Float)
    pos_in_range: Mapped[float | None] = mapped_column(Float)
    quote_vol_24h: Mapped[float | None] = mapped_column(Float)
    vwap_24h: Mapped[float | None] = mapped_column(Float)
    rsi_1h: Mapped[float | None] = mapped_column(Float)
    rs_vs_btc: Mapped[float | None] = mapped_column(Float)
    fib_236: Mapped[float | None] = mapped_column(Float)
    fib_382: Mapped[float | None] = mapped_column(Float)
    fib_500: Mapped[float | None] = mapped_column(Float)
    fib_618: Mapped[float | None] = mapped_column(Float)
    fib_786: Mapped[float | None] = mapped_column(Float)
    swing_shelf_7d: Mapped[float | None] = mapped_column(Float)
    swing_high_7d: Mapped[float | None] = mapped_column(Float)
    vol_7d_avg_usd: Mapped[float | None] = mapped_column(Float)
    # Flight recorder: the complete set of inputs the scorer read for this
    # symbol, as JSON. Without it a score can never be replayed, audited or
    # retrained against, because the inputs are gone by the next scan.
    feature_vector: Mapped[str | None] = mapped_column(Text)
    feature_version: Mapped[str | None] = mapped_column(String)


class Score(Base):
    __tablename__ = "scores"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_uuid)
    product_id: Mapped[str] = mapped_column(String, ForeignKey("symbols.product_id"), nullable=False, index=True)
    scan_run_id: Mapped[str] = mapped_column(String, ForeignKey("scan_runs.id"), nullable=False, index=True)
    computed_at: Mapped[str] = mapped_column(String, nullable=False, default=utcnow_iso)
    trade_direction: Mapped[str] = mapped_column(String, nullable=False, default="LONG")
    composite_score: Mapped[float] = mapped_column(Float, nullable=False)
    label: Mapped[str] = mapped_column(String, nullable=False)
    score_breakdown: Mapped[str] = mapped_column(Text, nullable=False)  # JSON
    # Belief state. `edge` is how good the evidence was; `coverage` is how much
    # of the model that evidence spans; `rank_key` is edge shrunk by coverage and
    # is what the scanner ranks by. Kept alongside `composite_score` (which now
    # carries rank_key) so historical rows remain comparable.
    edge: Mapped[float | None] = mapped_column(Float)
    coverage: Mapped[float | None] = mapped_column(Float)
    rank_key: Mapped[float | None] = mapped_column(Float)
    model_version: Mapped[str | None] = mapped_column(String)


class Ladder(Base):
    __tablename__ = "ladders"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_uuid)
    product_id: Mapped[str] = mapped_column(String, ForeignKey("symbols.product_id"), nullable=False, index=True)
    scan_run_id: Mapped[str] = mapped_column(String, ForeignKey("scan_runs.id"), nullable=False, index=True)

    computed_at: Mapped[str] = mapped_column(String, nullable=False, default=utcnow_iso)
    trade_direction: Mapped[str] = mapped_column(String, nullable=False, default="LONG")
    tranche_a_price: Mapped[float] = mapped_column(Float, nullable=False)
    tranche_b_price: Mapped[float] = mapped_column(Float, nullable=False)
    stop_price: Mapped[float] = mapped_column(Float, nullable=False)
    target_1_price: Mapped[float] = mapped_column(Float, nullable=False)
    target_2_price: Mapped[float | None] = mapped_column(Float)
    tranche_a_size_pct: Mapped[float] = mapped_column(Float, nullable=False, default=60.0)
    tranche_b_size_pct: Mapped[float] = mapped_column(Float, nullable=False, default=40.0)
    basis: Mapped[str | None] = mapped_column(Text)  # JSON
    chase_blocked: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Target-1 distance in R, as calibrated from realised excursions. Persisted so
    # that `sanitize_ladder_dict` — which rebuilds the dict from this row on every
    # read — honours the calibrated multiple instead of forcing T1 back out to its
    # hardcoded 2.0R default. Null on ladders written before it existed.
    target_r: Mapped[float | None] = mapped_column(Float)


class Watch(Base):
    __tablename__ = "watches"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_uuid)
    product_id: Mapped[str] = mapped_column(String, ForeignKey("symbols.product_id"), nullable=False)
    ladder_id: Mapped[str | None] = mapped_column(String, ForeignKey("ladders.id"))
    zone: Mapped[str] = mapped_column(String, nullable=False)  # TRANCHE_A | TRANCHE_B | BREAKOUT | INVALIDATION
    zone_price: Mapped[float] = mapped_column(Float, nullable=False)
    entry_price: Mapped[float | None] = mapped_column(Float)
    exit_price: Mapped[float | None] = mapped_column(Float)
    opened_at: Mapped[str] = mapped_column(String, nullable=False, default=utcnow_iso)
    closed_at: Mapped[str | None] = mapped_column(String)
    close_reason: Mapped[str | None] = mapped_column(String)
    is_active: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_uuid)
    product_id: Mapped[str] = mapped_column(String, ForeignKey("symbols.product_id"), nullable=False)
    scan_run_id: Mapped[str | None] = mapped_column(String, ForeignKey("scan_runs.id"))
    watch_id: Mapped[str | None] = mapped_column(String, ForeignKey("watches.id"))
    alert_type: Mapped[str] = mapped_column(String, nullable=False)
    price_at_alert: Mapped[float] = mapped_column(Float, nullable=False)
    zone_price: Mapped[float | None] = mapped_column(Float)
    zone_tolerance_pct: Mapped[float | None] = mapped_column(Float)
    label_at_alert: Mapped[str | None] = mapped_column(String)
    score_at_alert: Mapped[float | None] = mapped_column(Float)
    ladder_snapshot: Mapped[str | None] = mapped_column(Text)  # JSON
    dedupe_key: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False, default=utcnow_iso)
    delivered_at: Mapped[str | None] = mapped_column(String)
    suppressed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    suppressed_until: Mapped[str | None] = mapped_column(String)
    dismissed_by_user: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class UserSetting(Base):
    __tablename__ = "user_settings"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False, default=utcnow_iso)
    description: Mapped[str | None] = mapped_column(Text)


class HistoricalCandle(Base):
    __tablename__ = "historical_candles"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_uuid)
    symbol: Mapped[str] = mapped_column(String, nullable=False, index=True)
    granularity: Mapped[int] = mapped_column(Integer, nullable=False)  # 3600 (1h), 86400 (1d), 900 (15m), 21600 (6h)
    timestamp: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    open: Mapped[float] = mapped_column(Float, nullable=False)
    high: Mapped[float] = mapped_column(Float, nullable=False)
    low: Mapped[float] = mapped_column(Float, nullable=False)
    close: Mapped[float] = mapped_column(Float, nullable=False)
    volume: Mapped[float] = mapped_column(Float, nullable=False)


class SymbolListingBound(Base):
    __tablename__ = "symbol_listing_bounds"

    product_id: Mapped[str] = mapped_column(String, primary_key=True)
    first_candle_ts: Mapped[int] = mapped_column(Integer, nullable=False)
    last_candle_ts: Mapped[int] = mapped_column(Integer, nullable=False)
    total_candles: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[str] = mapped_column(String, nullable=False, default=utcnow_iso)


class BacktestRun(Base):
    __tablename__ = "backtest_runs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False, default=utcnow_iso)
    start_ts: Mapped[int] = mapped_column(Integer, nullable=False)
    end_ts: Mapped[int] = mapped_column(Integer, nullable=False)
    symbols_count: Mapped[int] = mapped_column(Integer, nullable=False)
    windows_count: Mapped[int] = mapped_column(Integer, nullable=False)
    survivorship_bias_note: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="universe = currently-listed symbols, survivorship bias not corrected",
    )
    config_snapshot: Mapped[str | None] = mapped_column(Text)  # JSON


class WalkForwardWindowResult(Base):
    __tablename__ = "walk_forward_window_results"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_uuid)
    backtest_run_id: Mapped[str] = mapped_column(
        String, ForeignKey("backtest_runs.id"), nullable=False, index=True
    )
    strategy_candidate: Mapped[str] = mapped_column(String, nullable=False)
    window_index: Mapped[int] = mapped_column(Integer, nullable=False)
    train_start_ts: Mapped[int] = mapped_column(Integer, nullable=False)
    train_end_ts: Mapped[int] = mapped_column(Integer, nullable=False)
    test_start_ts: Mapped[int] = mapped_column(Integer, nullable=False)
    test_end_ts: Mapped[int] = mapped_column(Integer, nullable=False)
    trades_count: Mapped[int] = mapped_column(Integer, nullable=False)
    win_rate: Mapped[float] = mapped_column(Float, nullable=False)
    avg_r: Mapped[float] = mapped_column(Float, nullable=False)
    max_drawdown_pct: Mapped[float] = mapped_column(Float, nullable=False)
    l2_approximated: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    details_json: Mapped[str | None] = mapped_column(Text)


class ShadowPipeline(Base):
    __tablename__ = "shadow_pipelines"

    pipeline_version: Mapped[str] = mapped_column(String, primary_key=True)
    candidate_name: Mapped[str] = mapped_column(String, nullable=False)
    staged_at: Mapped[str] = mapped_column(String, nullable=False, default=utcnow_iso)
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    target_sample_size: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    status: Mapped[str] = mapped_column(String, nullable=False, default="STAGED")  # STAGED | ELIGIBLE | PROMOTED | DISCARDED
    config_json: Mapped[str] = mapped_column(Text, nullable=False)
    promoted_at: Mapped[str | None] = mapped_column(String)


class CatalystSignal(Base):
    """Catalyst intelligence signal — one row per scrape cycle per symbol.

    Rows older than 24 hours (expires_at < now) are treated as stale and
    filtered out at query time.  They are **not** deleted immediately so that
    the daemon can compute a 7-day rolling average volume from history.
    """

    __tablename__ = "catalyst_signals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    coin_id: Mapped[str] = mapped_column(String(50), nullable=False)

    # Composite catalyst score [0, 100]
    catalyst_score: Mapped[float] = mapped_column(Float, nullable=False)
    priority_tier: Mapped[str] = mapped_column(String(10), nullable=False)  # CRITICAL|HIGH|WATCH|NOISE

    # Score components
    volume_surge_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    dev_activity_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    news_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    github_stars_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    # Raw metrics (preserved for display + volume history)
    volume_surge_ratio: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    volume_24h: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    commit_count_4w: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pr_merged_4w: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    github_stars: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # News
    top_headline: Mapped[str | None] = mapped_column(String(300))
    catalyst_keywords: Mapped[str | None] = mapped_column(String(500))  # comma-separated

    # Scorer integration: bonus injected into scorer.py macro_ix
    scorer_boost: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    # Timestamps
    scraped_at: Mapped[datetime] = mapped_column(nullable=False, default=lambda: datetime.now(UTC))
    expires_at: Mapped[datetime] = mapped_column(nullable=False)
