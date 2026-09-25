"""A/B the new scorer against the stored scores, on identical inputs.

The `composite_score` column was written by the old scorer. The `features` row is
the input it was given. So replaying those same rows through the new scorer is a
true like-for-like comparison — same symbols, same data, different brain.

Reads the live DB. No writes.
"""
from __future__ import annotations

import sqlite3
import sys
from collections import Counter

sys.path.insert(0, "backend")
from tpt.config.settings import settings  # noqa: E402
from tpt.config.strategy import load_strategy  # noqa: E402
from tpt.engine.scorer import score  # noqa: E402

FEATURE_KEYS = (
    "last_price", "day_open", "day_high", "day_low", "day_change_pct", "pos_in_range",
    "quote_vol_24h", "vwap_24h", "rsi_1h", "rs_vs_btc", "fib_236", "fib_382", "fib_500",
    "fib_618", "fib_786", "swing_shelf_7d", "swing_high_7d", "vol_7d_avg_usd",
)

conn = sqlite3.connect(settings.sqlite_path)
conn.row_factory = sqlite3.Row
cfg = load_strategy()

latest = conn.execute("""
    SELECT id FROM scan_runs WHERE status != 'RUNNING'
      AND (SELECT COUNT(*) FROM scores s WHERE s.scan_run_id = scan_runs.id) > 0
    ORDER BY started_at DESC LIMIT 1
""").fetchone()[0]

rows = [dict(r) for r in conn.execute("""
    SELECT f.*, s.composite_score AS old_score, s.trade_direction AS old_dir
    FROM features f JOIN scores s
      ON s.product_id = f.product_id AND s.scan_run_id = f.scan_run_id
    WHERE f.scan_run_id = ?
""", (latest,))]

print(f"DB: {settings.sqlite_path}")
print(f"scan: {latest} | symbols: {len(rows)}")


def new_score_for(row):
    """Replay the stored inputs through the new scorer, keeping the old direction."""
    feats = {k: row[k] for k in FEATURE_KEYS if k in row}
    feats["product_id"] = row["product_id"]
    return score(feats, cfg.scoring, trade_direction=row["old_dir"] or "LONG")


results = []
for r in rows:
    sd = new_score_for(r)
    results.append({
        "pid": r["product_id"],
        "old": r["old_score"],
        "new": sd["clamped"],
        "edge": sd["edge"],
        "cov": sd["coverage"],
        "band": sd["coverage_band"],
    })

print("\n=== coverage is now reported instead of hidden ===")
bands = Counter(x["band"] for x in results)
for band, n in bands.most_common():
    subset = [x for x in results if x["band"] == band]
    avg_cov = sum(x["cov"] for x in subset) / len(subset)
    print(f"  {band:<8} n={n:4d}  avg coverage {avg_cov:.2f}")

print("\n=== score distribution: stored (old) vs replayed (new) ===")
for label, key in (("stored/old", "old"), ("replayed/new", "new")):
    vals = [x[key] for x in results]
    vals_sorted = sorted(vals)
    n70 = sum(1 for v in vals if v >= 70)
    print(f"  {label:<13} mean {sum(vals)/len(vals):5.1f}  median {vals_sorted[len(vals)//2]:5.1f}"
          f"  max {max(vals):5.1f}  >=70: {n70:4d} ({100*n70/len(vals):4.1f}%)")

print("\n=== leaderboard ===")
print(f"  {'#':>3}  {'OLD (stored)':<22}{'NEW (rank_key)':<22}")
old_top = sorted(results, key=lambda x: -x["old"])[:10]
new_top = sorted(results, key=lambda x: -x["new"])[:10]
for i in range(10):
    o, n = old_top[i], new_top[i]
    print(f"  {i+1:>3}  {o['pid']:<13}{o['old']:6.1f}      {n['pid']:<13}{n['new']:6.1f}")

overlap = {x["pid"] for x in old_top[:10]} & {x["pid"] for x in new_top[:10]}
print(f"\n  top-10 overlap between the two rankings: {len(overlap)}/10")

print("\n=== what happened to the old high scorers ===")
old_ge70 = [x for x in results if x["old"] >= 70]
if old_ge70:
    dropped = sum(1 for x in old_ge70 if x["new"] < 70)
    avg_delta = sum(x["new"] - x["old"] for x in old_ge70) / len(old_ge70)
    print(f"  symbols scoring >=70 under the old scorer : {len(old_ge70)}")
    print(f"  ...that fall below 70 under the new one   : {dropped} ({100*dropped/len(old_ge70):.0f}%)")
    print(f"  average score change (new - old)          : {avg_delta:+.1f} points")

print("\n  the scores whose rank rests on the least evidence:")
worst = sorted([x for x in results if x["old"] >= 70], key=lambda x: (x["cov"], -x["old"]))[:8]
for x in worst:
    print(f"    {x['pid']:<14} old {x['old']:5.1f} -> new {x['new']:5.1f}"
          f"   coverage {x['cov']:.2f} ({x['band']})")

conn.close()
