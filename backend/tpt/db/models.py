"""SQLAlchemy ORM models for all TPT tables.

TODO (M0): Implement all models per DATA_MODEL.md.
"""
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
    product_id: Mapped[str] = mapped_column(String, ForeignKey("symbols.product_id"), nullable=False)
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


class Score(Base):
    __tablename__ = "scores"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_uuid)
    product_id: Mapped[str] = mapped_column(String, ForeignKey("symbols.product_id"), nullable=False)
    scan_run_id: Mapped[str] = mapped_column(String, ForeignKey("scan_runs.id"), nullable=False, index=True)
    computed_at: Mapped[str] = mapped_column(String, nullable=False, default=utcnow_iso)
    trade_direction: Mapped[str] = mapped_column(String, nullable=False, default="LONG")
    composite_score: Mapped[float] = mapped_column(Float, nullable=False)
    label: Mapped[str] = mapped_column(String, nullable=False)
    score_breakdown: Mapped[str] = mapped_column(Text, nullable=False)  # JSON


class Ladder(Base):
    __tablename__ = "ladders"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_uuid)
    product_id: Mapped[str] = mapped_column(String, ForeignKey("symbols.product_id"), nullable=False)
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
