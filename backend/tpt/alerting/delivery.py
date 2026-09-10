"""Alert delivery worker — quiet hours + morning digest.

TODO (M3): Implement delivery logic.
"""
from __future__ import annotations

from datetime import datetime


def should_deliver(alert: dict, now_utc: datetime, quiet_start: str, quiet_end: str, tz_name: str) -> bool:
    """
    Return True if alert should be delivered now (outside quiet hours).

    TODO (M3): implement proper quiet hour check.
    - Convert now_utc to tz_name timezone
    - Parse quiet_start / quiet_end as HH:MM
    - Return False during quiet window
    """
    raise NotImplementedError("M3: implement should_deliver()")


async def deliver_pending_alerts() -> int:
    """
    Deliver all pending (undelivered, non-suppressed) alerts.
    Returns number of alerts delivered.

    TODO (M3): Implement.
    """
    raise NotImplementedError("M3: implement deliver_pending_alerts()")


async def deliver_morning_digest() -> int:
    """
    Bundle all suppressed alerts into a DIGEST and deliver.
    Called at digest_time (default 08:00 Nairobi).

    TODO (M3): Implement.
    """
    raise NotImplementedError("M3: implement deliver_morning_digest()")
