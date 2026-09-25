"""Unit tests for the exit-calibration estimator."""
from tpt.engine.exits import (
    MIN_SAMPLES,
    PROVISIONAL_MIN,
    calibrate_targets,
    excursion_from_signal,
    excursion_profile,
    expected_value,
    hit_probability,
)


def _signal(mfe_pct: float, mae_pct: float, entry: float = 100.0, stop: float = 98.0) -> dict:
    """Entry 100 / stop 98 => risk 2% of entry, so mfe% / 2 == R."""
    return {"entry_price": entry, "sl_price": stop, "mfe": mfe_pct, "mae": mae_pct}


def test_excursion_converts_percent_to_r() -> None:
    e = excursion_from_signal(_signal(mfe_pct=6.0, mae_pct=-2.0))
    assert e is not None
    assert abs(e.risk_pct - 2.0) < 1e-9
    assert abs(e.mfe_r - 3.0) < 1e-9
    assert abs(e.mae_r + 1.0) < 1e-9


def test_excursion_rejects_zero_risk() -> None:
    """Entry == stop is not a trade with infinite R; it is unusable."""
    assert excursion_from_signal(_signal(4.0, -1.0, entry=100.0, stop=100.0)) is None
    assert excursion_from_signal({"entry_price": None, "sl_price": 10.0, "mfe": 1, "mae": 0}) is None


def test_below_provisional_min_publishes_no_target() -> None:
    """With too few trades there is no basis for a target, provisional or not."""
    rows = [_signal(6.0, -2.0) for _ in range(PROVISIONAL_MIN - 1)]
    est = calibrate_targets(rows)
    assert est.sufficient is False
    assert est.provisional is True
    assert est.r_multiple is None
    assert "required" in (est.reason or "")


def test_between_provisional_min_and_min_samples_publishes_a_provisional_target() -> None:
    """A reachable provisional target is published rather than nothing.

    This is the change that unfroze the win rate. Previously the estimator
    refused below MIN_SAMPLES, which left the ladder on its hardcoded 2.0R target
    while the best excursion ever recorded was 0.72R — so no trade could win.
    Refusing to answer was not the safe option; it was the one that made every
    outcome a loss or a break-even.
    """
    rows = [_signal(6.0, -2.0) for _ in range(MIN_SAMPLES - 1)]
    est = calibrate_targets(rows)
    assert est.sufficient is False
    assert est.provisional is True
    assert est.r_multiple is not None
    assert est.n == MIN_SAMPLES - 1
    assert "below" in (est.reason or "")


def test_picks_the_ev_maximising_target() -> None:
    """30 trades reach 3R, 70 reach only 0.5R.

    With the grid extended below 1R — without which a reachable target cannot be
    expressed at all — the EVs are:
      0.25R -> +0.25    0.50R -> +0.50    0.75R -> -0.48
      1R    -> -0.40    3R    -> +0.20    4R    -> -1.00

    Every trade reaches 0.5R, so that is the maximum: a certain +0.5R beats a 30%
    shot at +3R. The estimator must find that rather than assume the 2.0R floor.
    """
    rows = [_signal(6.0, -2.0) for _ in range(30)] + [_signal(1.0, -2.0) for _ in range(70)]
    est = calibrate_targets(rows)
    assert est.sufficient is True
    assert est.n == 100
    assert est.r_multiple == 0.5
    assert est.ev_r is not None and est.ev_r > 0


def test_prefers_a_bigger_target_when_the_smaller_one_is_not_certain() -> None:
    """Two thirds reach 3R, the rest only 0.25R.

    0.25R is reached by everyone -> EV +0.25, but 3R is reached by two thirds ->
    EV +1.68, so 3R wins. The estimator should not simply chase the nearest
    target; it should chase expected value.
    """
    rows = [_signal(6.0, -2.0) for _ in range(67)] + [_signal(0.5, -2.0) for _ in range(33)]
    est = calibrate_targets(rows)
    assert est.r_multiple == 3.0


def test_negative_ev_is_reported_rather_than_hidden() -> None:
    """Every trade reaches only 0.2R, which is below the smallest grid target.

    Nothing on the grid is reachable, so every EV is -1. That is not a target
    problem — it means the entries show no edge, and the reason must say so
    rather than quietly returning a number.
    """
    rows = [_signal(0.4, -2.0) for _ in range(50)]
    est = calibrate_targets(rows)
    assert est.ev_r is not None and est.ev_r < 0
    assert "no edge" in (est.reason or "")


def test_hit_probability_and_ev_are_monotonic_in_target() -> None:
    rows = [_signal(6.0, -2.0) for _ in range(50)]
    ex = [e for e in (excursion_from_signal(r) for r in rows) if e is not None]
    # All trades reach 3R, none reach 4R.
    assert hit_probability(ex, 1.0) == 1.0
    assert hit_probability(ex, 3.0) == 1.0
    assert hit_probability(ex, 4.0) == 0.0
    # With p==1, EV is just the target.
    assert abs(expected_value(ex, 3.0) - 3.0) < 1e-9


def test_profile_reports_the_whole_curve() -> None:
    rows = [_signal(6.0, -2.0) for _ in range(45)]
    prof = excursion_profile(rows)
    assert len(prof) > 0
    assert all("r_multiple" in p and "hit_probability" in p and "ev_r" in p for p in prof)
