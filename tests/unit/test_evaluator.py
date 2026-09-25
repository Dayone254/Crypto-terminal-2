"""Unit tests for the evaluator's exit-management arithmetic."""
from tpt.engine.evaluator import break_even_arm_pct


def test_break_even_arms_in_r_not_percent() -> None:
    """The stop moves to entry once the trade has earned its own risk back.

    This used to be a flat ``mfe >= 2.5`` PERCENT, so on a 5% stop it armed at
    0.5R. Every one of the eight break-evens in the first 22 closed trades had
    MFE just over 2.5% with MAE under 1.24% — the signature of a trigger firing
    before the trade had earned anything.
    """
    # 5% risk: one R of favourable excursion is 5%, not 2.5%.
    assert break_even_arm_pct(risk_pct=5.0, be_arm_r=1.0) == 5.0
    # 1% risk: one R is 1%.
    assert break_even_arm_pct(risk_pct=1.0, be_arm_r=1.0) == 1.0


def test_break_even_scales_with_the_configured_multiple() -> None:
    """Raising be_arm_r lets winners breathe before the stop is pulled to entry."""
    assert break_even_arm_pct(risk_pct=4.0, be_arm_r=1.5) == 6.0
    assert break_even_arm_pct(risk_pct=4.0, be_arm_r=0.5) == 2.0


def test_break_even_falls_back_when_there_is_no_risk_to_scale_by() -> None:
    """A signal with no usable risk distance has no R to multiply.

    It must fall back to the old constant rather than returning zero, which would
    arm the break-even stop on the very first candle.
    """
    assert break_even_arm_pct(risk_pct=0.0, be_arm_r=1.0) == 2.5
    assert break_even_arm_pct(risk_pct=-1.0, be_arm_r=1.0) == 2.5
