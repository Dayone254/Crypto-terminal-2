"""Quiet-hours evaluation in a configured timezone.

Kept separate from the delivery worker so alert generation (which needs only the
suppression *flag*) and delivery both share one implementation.
"""
from __future__ import annotations

from datetime import UTC, datetime, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def _parse_hhmm(value: str) -> int:
    """Parse 'HH:MM' into minutes-past-midnight."""
    try:
        hh, mm = value.strip().split(":")[:2]
        return int(hh) * 60 + int(mm)
    except (ValueError, AttributeError) as exc:
        raise ValueError(f"Invalid HH:MM time: {value!r}") from exc


def _to_local(now_utc: datetime, tz_name: str) -> datetime:
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=UTC)
    try:
        zone: tzinfo = ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError):
        # Unknown timezone — fall back to UTC rather than crashing the scanner.
        zone = UTC
    return now_utc.astimezone(zone)


def is_quiet_now(
    now_utc: datetime,
    quiet_start: str = "00:00",
    quiet_end: str = "07:59",
    tz_name: str = "Africa/Nairobi",
) -> bool:
    """True when `now_utc` falls inside the quiet window (local to `tz_name`).

    Handles windows that wrap past midnight (e.g. 22:00 -> 07:00).
    """
    start = _parse_hhmm(quiet_start)
    end = _parse_hhmm(quiet_end)
    if start == end:
        return False

    local = _to_local(now_utc, tz_name)
    minutes = local.hour * 60 + local.minute

    if start < end:
        return start <= minutes < end
    return minutes >= start or minutes < end


def should_deliver(
    alert: dict | None,
    now_utc: datetime,
    quiet_start: str,
    quiet_end: str,
    tz_name: str,
) -> bool:
    """Return True if the alert should be delivered now (outside quiet hours)."""
    return not is_quiet_now(now_utc, quiet_start, quiet_end, tz_name)
