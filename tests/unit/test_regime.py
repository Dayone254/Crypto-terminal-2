"""Unit tests for market-regime detection and the continuous macro thrust."""
from tpt.engine.regime import beta_state_from_thrust, macro_thrust


def test_macro_thrust_averages_whatever_inputs_exist() -> None:
    # 20 flat 1h closes then one 10% above the window -> SMA term is +10.
    closes = [100.0] * 20 + [110.0]
    sma_only = macro_thrust(closes, None)
    assert abs(sma_only - 10.0) < 1e-9

    # Adding a day change averages the two components rather than adding them,
    # so neither term can dominate the penalty on its own.
    both = macro_thrust(closes, 0.0)
    assert abs(both - 5.0) < 1e-9

    # A pure day change with no candles still yields a usable number.
    assert macro_thrust(None, -4.0) == -4.0


def test_macro_thrust_is_sign_correct() -> None:
    assert macro_thrust(None, -3.0) < 0
    assert macro_thrust(None, 3.0) > 0


def test_no_input_yields_no_thrust() -> None:
    """Absence of information must not become a phantom signal."""
    assert macro_thrust(None, None) == 0.0
    assert macro_thrust([], None) == 0.0
    # Too few closes for the SMA window -> fall back to the day change alone.
    assert macro_thrust([100.0] * 5, -3.0) == -3.0


def test_beta_state_thresholds() -> None:
    assert beta_state_from_thrust(-2.0) == "DUMPING"
    assert beta_state_from_thrust(2.0) == "PUMPING"
    assert beta_state_from_thrust(0.5) == "RANGING"
    # Boundaries are inclusive.
    assert beta_state_from_thrust(-1.5) == "DUMPING"
    assert beta_state_from_thrust(1.5) == "PUMPING"
