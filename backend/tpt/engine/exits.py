"""Exit calibration from realised excursions.

Every closed signal already stores how far the trade ran in favour (MFE) and
against (MAE), as a percentage of the fill price. That is precisely the data
needed to answer "where should target 1 have been?" — and nothing has ever read
it. The ladder places T1 at a fixed 2.0R floor regardless of what the market
actually delivers, which is why every signal in the ledger carries a target of
exactly 2.0R: the floor, never above it.

This module converts each closed trade's excursions into R multiples and
estimates the empirical probability of reaching a given target, then picks the
target that maximises expected value under a full-loss-at-1R assumption.

It deliberately refuses to answer below ``MIN_SAMPLES`` closed trades. With a
handful of observations the "optimal" target is pure noise, and publishing one
would be worse than publishing nothing — the point of this whole exercise is to
stop the system asserting things its evidence cannot support.

Pure functions over already-fetched rows. No I/O.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

# Below this many closed trades the estimator returns `sufficient=True` only for
# guidance, and marks the answer provisional. Raise it as the sample grows; do
# not lower it to get an answer.
MIN_SAMPLES = 40

# Between this and MIN_SAMPLES the estimator still returns a target, but flags it
# `provisional=True`. The reason is empirical: the ladder was publishing a 2.0R
# target while the best favourable excursion ever recorded across 22 closed
# trades was 0.72R. Publishing nothing was not the safe option — publishing an
# unreachable target was the unsafe one, because it makes a win arithmetically
# impossible and the win rate meaningless.
PROVISIONAL_MIN = 8

# Target grid, in R multiples. It reaches well below 1.0R on purpose: with a 3-5%
# stop and typical favourable excursions of 1-3%, the reachable targets live
# under 1R, and a grid that starts at 1.0 can only ever return an unreachable
# answer. The upper end matches the ladder's own 8.0R ceiling.
TARGET_GRID: tuple[float, ...] = (
    0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 8.0
)


@dataclass(frozen=True)
class Excursion:
    """One closed trade, expressed in R multiples."""

    risk_pct: float
    mfe_r: float
    mae_r: float


@dataclass(frozen=True)
class TargetEstimate:
    """What the observed excursions say about where T1 should sit."""

    sufficient: bool
    n: int
    r_multiple: float | None
    ev_r: float | None
    hit_probability: float | None
    reason: str | None = None
    # True when the sample is big enough to act on but too small to trust. The
    # target is still returned — refusing to publish a reachable one is what put
    # the ladder on an unreachable 2.0R floor in the first place.
    provisional: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "sufficient": self.sufficient,
            "provisional": self.provisional,
            "n": self.n,
            "r_multiple": self.r_multiple,
            "ev_r": self.ev_r,
            "hit_probability": self.hit_probability,
            "reason": self.reason,
        }


def excursion_from_signal(row: dict[str, Any]) -> Excursion | None:
    """Convert one signals row into R multiples, or None if it is unusable.

    Risk is the distance from entry to stop as a share of entry; MFE/MAE are
    stored as percentages of the fill price, so dividing by that risk expresses
    them in R.
    """
    entry = _num(row.get("entry_price"))
    stop = _num(row.get("sl_price"))
    mfe = _num(row.get("mfe"))
    mae = _num(row.get("mae"))
    if entry is None or stop is None or entry <= 0:
        return None

    risk_pct = abs(entry - stop) / entry * 100.0
    if risk_pct <= 0:
        return None

    return Excursion(
        risk_pct=risk_pct,
        mfe_r=(mfe or 0.0) / risk_pct,
        mae_r=(mae or 0.0) / risk_pct,
    )


def hit_probability(excursions: Iterable[Excursion], r_multiple: float) -> float:
    """Fraction of trades whose favourable excursion reached ``r_multiple``.

    An upper bound rather than a true probability: MFE records that the level was
    touched, not that it was touched before the stop. It is still the right input
    for target selection — it says what the market offered, which is the question
    a target is answering.
    """
    rows = list(excursions)
    if not rows:
        return 0.0
    return sum(1 for e in rows if e.mfe_r >= r_multiple) / len(rows)


def expected_value(excursions: Iterable[Excursion], r_multiple: float) -> float:
    """EV in R for a target at ``r_multiple`` with a full loss at -1R."""
    p = hit_probability(excursions, r_multiple)
    return p * r_multiple - (1.0 - p) * 1.0


def calibrate_targets(
    excursion_rows: Iterable[dict[str, Any]],
    grid: tuple[float, ...] = TARGET_GRID,
    min_samples: int = MIN_SAMPLES,
    provisional_min: int = PROVISIONAL_MIN,
) -> TargetEstimate:
    """Estimate the EV-maximising target from realised trades.

    Callers must pass **closed** trades only. A still-open signal has zero
    recorded excursion, which means "not yet measured" rather than "went
    nowhere"; feeding those in drags every reach probability toward zero.

    Three outcomes:

    * ``n >= min_samples`` — a firm estimate.
    * ``provisional_min <= n < min_samples`` — the EV-best target, flagged
      ``provisional``. Published because the alternative in production was not
      "no target" but a hardcoded 2.0R one that no trade could reach.
    * ``n < provisional_min`` — no target at all.

    When no point on the grid has positive expected value under a full loss at
    1R, that is reported in ``reason``. It means the *entries* have no
    demonstrated edge, and no choice of target will manufacture one.
    """
    excursions = [e for e in (excursion_from_signal(r) for r in excursion_rows) if e is not None]
    n = len(excursions)

    if n == 0:
        return TargetEstimate(
            sufficient=False,
            provisional=True,
            n=0,
            r_multiple=None,
            ev_r=None,
            hit_probability=None,
            reason="no closed trades with usable risk — no basis for a target",
        )

    scored = [(r, expected_value(excursions, r), hit_probability(excursions, r)) for r in grid]
    # Highest EV wins; on a tie prefer the nearer target, since it is the one more
    # likely to actually fill.
    best_r, best_ev, best_p = max(scored, key=lambda t: (t[1], -t[0]))
    negative_ev = best_ev < 0

    if n >= min_samples and not negative_ev:
        return TargetEstimate(
            sufficient=True,
            provisional=False,
            n=n,
            r_multiple=best_r,
            ev_r=round(best_ev, 3),
            hit_probability=round(best_p, 3),
        )

    if n < provisional_min:
        return TargetEstimate(
            sufficient=False,
            provisional=True,
            n=n,
            r_multiple=None,
            ev_r=round(best_ev, 3),
            hit_probability=None,
            reason=(
                f"{n} usable closed trade(s); {provisional_min} required before "
                f"publishing even a provisional target"
            ),
        )

    parts = []
    if n < min_samples:
        parts.append(f"{n} closed trade(s), below the {min_samples} for a firm estimate")
    if negative_ev:
        parts.append(
            "no grid target has positive EV against a 1R stop — the entries show "
            "no edge, and no target choice creates one"
        )
    return TargetEstimate(
        sufficient=False,
        provisional=True,
        n=n,
        r_multiple=best_r,
        ev_r=round(best_ev, 3),
        hit_probability=round(best_p, 3),
        reason="; ".join(parts),
    )


def excursion_profile(
    excursion_rows: Iterable[dict[str, Any]],
    grid: tuple[float, ...] = TARGET_GRID,
) -> list[dict[str, Any]]:
    """The full reach/EV curve, for reporting and plotting."""
    excursions = [e for e in (excursion_from_signal(r) for r in excursion_rows) if e is not None]
    n = len(excursions)
    if n == 0:
        return []
    out = []
    for r in grid:
        out.append({
            "r_multiple": r,
            "n": n,
            "hit_probability": round(hit_probability(excursions, r), 3),
            "ev_r": round(expected_value(excursions, r), 3),
        })
    return out


def _num(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
