"""Unit tests for alert generation and quiet-hours evaluation."""
from datetime import UTC, datetime

from tpt.alerting.alerter import build_dedupe_key, generate_alerts
from tpt.alerting.quiet_hours import is_quiet_now, should_deliver
from tpt.config.strategy import AlertConfig


def _candidate(price: float = 100.0, tranche_a: float = 99.9, tranche_b: float = 95.0,
               stop: float = 94.0, direction: str = "LONG") -> dict:
    return {
        "product_id": "ETH-USD",
        "last_price": price,
        "label": "ENTRY_ZONE",
        "composite_score": 75.0,
        "trade_direction": direction,
        "ladder": {
            "tranche_a_price": tranche_a,
            "tranche_b_price": tranche_b,
            "stop_price": stop,
            "target_1_price": 110.0,
        },
    }


# ── Quiet hours ───────────────────────────────────────────────────────────────

def test_quiet_hours_inside_window() -> None:
    # 02:00 UTC == 05:00 Nairobi -> inside 00:00-07:59
    now = datetime(2026, 1, 1, 2, 0, tzinfo=UTC)
    assert is_quiet_now(now, "00:00", "07:59", "Africa/Nairobi") is True


def test_quiet_hours_outside_window() -> None:
    # 12:00 UTC == 15:00 Nairobi -> outside
    now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    assert is_quiet_now(now, "00:00", "07:59", "Africa/Nairobi") is False


def test_quiet_hours_window_wrapping_midnight() -> None:
    quiet = ("22:00", "07:00")
    at_2300 = datetime(2026, 1, 1, 23, 0, tzinfo=UTC)
    at_0300 = datetime(2026, 1, 1, 3, 0, tzinfo=UTC)
    at_1200 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    assert is_quiet_now(at_2300, *quiet, "UTC") is True
    assert is_quiet_now(at_0300, *quiet, "UTC") is True
    assert is_quiet_now(at_1200, *quiet, "UTC") is False


def test_neutral_window_never_quiet() -> None:
    now = datetime(2026, 1, 1, 3, 0, tzinfo=UTC)
    assert is_quiet_now(now, "08:00", "08:00", "UTC") is False


def test_should_deliver_inverts_quiet_hours() -> None:
    quiet_now = datetime(2026, 1, 1, 2, 0, tzinfo=UTC)
    assert should_deliver({}, quiet_now, "00:00", "07:59", "Africa/Nairobi") is False
    awake = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    assert should_deliver({}, awake, "00:00", "07:59", "Africa/Nairobi") is True


# ── Alert generation ──────────────────────────────────────────────────────────

def test_zone_entry_emits_alert_and_opens_watch() -> None:
    alerts = generate_alerts([_candidate()], {}, AlertConfig())
    assert len(alerts) == 1
    alert = alerts[0]
    assert alert["alert_type"] == "ZONE_A_ENTRY"
    assert alert["watch_action"] == "OPEN"
    assert alert["product_id"] == "ETH-USD"


def test_dedupe_key_suppresses_repeat() -> None:
    candidate = _candidate()
    key = build_dedupe_key("ETH-USD", "ZONE_A_ENTRY", candidate["ladder"]["tranche_a_price"])
    alerts = generate_alerts([candidate], {}, AlertConfig(), recent_dedupe_keys={key})
    assert alerts == []


def test_existing_watch_prevents_duplicate_entry() -> None:
    alerts = generate_alerts([_candidate()], {("ETH-USD", "TRANCHE_A"): {"zone": "TRANCHE_A"}}, AlertConfig())
    assert alerts == []


def test_price_exit_closes_watch() -> None:
    # Price far away from the tranche-A level -> close the active watch.
    candidate = _candidate(price=110.0)
    alerts = generate_alerts([candidate], {("ETH-USD", "TRANCHE_A"): {"zone": "TRANCHE_A"}}, AlertConfig())
    closes = [a for a in alerts if a["watch_action"] == "CLOSE"]
    assert len(closes) == 1
    assert closes[0]["close_reason"] == "PRICE_EXIT"


def test_invalidation_beats_zone_entry() -> None:
    # Price has crossed the stop -> invalidation, not a fresh zone entry.
    candidate = _candidate(price=93.0)
    alerts = generate_alerts([candidate], {("ETH-USD", "TRANCHE_A"): {"zone": "TRANCHE_A"}}, AlertConfig())
    assert alerts, "expected an invalidation alert"
    assert all(a["alert_type"] == "INVALIDATION" for a in alerts)
    assert all(a["close_reason"] == "INVALIDATION" for a in alerts)


def test_quiet_hours_marks_alert_suppressed() -> None:
    quiet = datetime(2026, 1, 1, 2, 0, tzinfo=UTC)  # 05:00 Nairobi
    alerts = generate_alerts([_candidate()], {}, AlertConfig(), now_utc=quiet)
    assert len(alerts) == 1
    assert alerts[0]["suppressed"] == 1


def test_shorts_invalidate_on_upward_break() -> None:
    # A SHORT is stopped out when price rises through the stop (above entry).
    candidate = _candidate(price=102.0, stop=101.0, direction="SHORT")
    alerts = generate_alerts([candidate], {("ETH-USD", "TRANCHE_A"): {"zone": "TRANCHE_A"}}, AlertConfig())
    assert any(a["alert_type"] == "INVALIDATION" for a in alerts)


def test_candidates_without_ladder_are_ignored() -> None:
    assert generate_alerts([{"product_id": "BTC-USD", "last_price": 1.0, "ladder": None}], {}, AlertConfig()) == []
