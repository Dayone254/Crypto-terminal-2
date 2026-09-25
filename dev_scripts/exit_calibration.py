"""Report what realised MFE/MAE say about where exits should sit.

Reads the live DB. No writes.
"""
from __future__ import annotations

import sqlite3
import sys

sys.path.insert(0, "backend")
from tpt.config.settings import settings  # noqa: E402
from tpt.engine.exits import (  # noqa: E402
    MIN_SAMPLES,
    calibrate_targets,
    excursion_from_signal,
    excursion_profile,
)

conn = sqlite3.connect(settings.sqlite_path)
conn.row_factory = sqlite3.Row

# Only CLOSED trades carry an excursion. A still-PENDING signal has mfe/mae of 0,
# which is absence of a measurement, not a trade that went nowhere — including
# them would drag every reach probability toward zero.
CLOSED = ("WIN", "LOSS", "BREAK_EVEN", "PARTIAL_WIN")

rows = [dict(r) for r in conn.execute(f"""
    SELECT symbol, label, trade_direction, status, entry_price, sl_price, tp_price, mfe, mae
    FROM signals
    WHERE mfe IS NOT NULL AND sl_price IS NOT NULL AND entry_price IS NOT NULL
      AND status IN {CLOSED}
    ORDER BY closed_at DESC
""")]
pending = conn.execute(
    "SELECT COUNT(*) FROM signals WHERE status = 'PENDING'"
).fetchone()[0]

print(f"DB: {settings.sqlite_path}")
print(f"closed signals with excursions recorded: {len(rows)}  ({pending} still pending, excluded)\n")

excursions = [e for e in (excursion_from_signal(r) for r in rows) if e is not None]
print(f"usable (non-zero risk): {len(excursions)}\n")

if excursions:
    paired = [(r, excursion_from_signal(r)) for r in rows]
    paired = [(r, e) for r, e in paired if e is not None]

    print("realised excursions, in R (1R = entry-to-stop distance):")
    print(f"  {'symbol':<14}{'dir':<6}{'status':<10}{'risk%':>7}{'MFE (R)':>10}{'MAE (R)':>10}")
    for r, e in paired:
        print(
            f"  {str(r['symbol'])[:13]:<14}{str(r['trade_direction'] or ''):<6}"
            f"{str(r['status'])[:9]:<10}{e.risk_pct:7.2f}{e.mfe_r:10.2f}{e.mae_r:10.2f}"
        )

    print("\ntarget reach curve (what the market actually delivered):")
    print(f"  {'target':>8}{'P(reach)':>12}{'EV (R)':>10}")
    for p in excursion_profile(rows):
        print(f"  {p['r_multiple']:>7.1f}R{p['hit_probability']:>12.2f}{p['ev_r']:>10.2f}")

est = calibrate_targets(rows)
print("\ncalibrated target:")
if est.sufficient:
    print(f"  T1 = {est.r_multiple}R  (P=hit {est.hit_probability}, EV {est.ev_r}R over n={est.n})")
else:
    print(f"  INSUFFICIENT DATA — {est.reason}")
    print(f"  (the ladder keeps its {2.0}R floor until this clears; no target is invented)")

print(f"\nminimum sample for a published target: {MIN_SAMPLES}")
conn.close()
