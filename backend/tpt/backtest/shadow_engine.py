"""Shadow-mode signal generation — candidates evaluated alongside the live pipeline.

The governance layer (backtest/shadow.py) stages candidate configs and promotes
them only after `min_shadow_sample_size` closed trades — but the scanner used to
stamp every signal `v2.0`, so a staged pipeline's sample count sat at zero
forever and promotion gated on a queue nothing fed.

This module closes that loop: after the live pipeline admits a setup, the SAME
evidence (features, scores, L2 book, calibration) is re-evaluated under each
staged candidate's config (min score / volume floor / ATR stop) and persisted as
a signal row stamped with the candidate's pipeline_version. The forward-testing
evaluator resolves those rows exactly like live ones, so every staged candidate
accrues an honest, independently-gated track record.

Rules:
- Shadow rows NEVER carry `v2.0` and live rows never carry a staged version —
  the ledger's pipeline_version column is the isolation boundary.
- Shadow evaluation is additive: it re-uses evidence the live scan already paid
  for. A candidate that produces no setup where live did produces no row.
- Nothing here can influence live admission, sizing, or alerts.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from tpt.config.strategy import StrategyConfig
from tpt.engine.labeler import label
from tpt.engine.ladder import compute_ladder, confirm_l2_structure, sanitize_ladder_dict

logger = logging.getLogger(__name__)

# Row shape mirrors the live pending/L2-rejected tuples plus pipeline_version
# and the resolved status, kept as a dict for readability at the insert site.
ShadowRecord = dict[str, Any]


def evaluate_shadow_candidates(
    *,
    staged: list[tuple[str, str, StrategyConfig, float | None]],
    product_id: str,
    features: dict[str, Any],
    composite_score: float,
    score_dict: dict[str, Any],
    trade_direction: str,
    regime: str,
    pinned: bool,
    target_r: float | None,
    scan_run_id: str,
) -> list[ShadowRecord]:
    """Re-evaluate one live-admitted setup under every staged candidate config.

    `staged` items are (pipeline_version, candidate_name, StrategyConfig copy
    with the candidate's overrides applied, calibrated target_r). Returns zero
    or one record per candidate — a candidate whose config does not admit this
    setup (score gate, volume floor, ladder R/R floor, L2 gate) contributes
    nothing, which is precisely the discriminating power shadow mode exists to
    measure.
    """
    records: list[ShadowRecord] = []

    for pipeline_version, candidate_name, cand_cfg, _tr in staged:
        sh_lbl = label(
            features, composite_score, cand_cfg.labeling,
            trade_direction=trade_direction, regime=regime,
        )
        if sh_lbl not in ("ENTRY_ZONE", "COILED"):
            continue

        sh_ladder = compute_ladder(
            product_id=product_id,
            features=features,
            lbl=sh_lbl,
            composite_score=composite_score,
            config=cand_cfg.ladder,
            pinned=pinned,
            trade_direction=trade_direction,
            regime=regime,
            target_r=target_r,
        )
        if not sh_ladder:
            continue
        sh_san = sanitize_ladder_dict(sh_ladder)
        if not sh_san or not sh_san.get("tranche_a_price"):
            continue

        # Same deterministic L2 gate the live path applies, with the same
        # soft-mode fallback — a shadow admission must be admissible under the
        # rules a live pipeline would face.
        l2_bids = features.get("l2_bids")
        l2_asks = features.get("l2_asks")
        gate = confirm_l2_structure(
            symbol=product_id,
            trade_direction=trade_direction,
            entry_price=sh_san["tranche_a_price"],
            l2_bids=l2_bids,
            l2_asks=l2_asks,
            quote_vol_24h=features.get("quote_vol_24h"),
            soft_mode=not bool(l2_bids or l2_asks),
        )
        status = "PENDING" if gate.get("passed") else "L2_REJECTED"

        records.append({
            "scan_run_id": scan_run_id,
            "symbol": product_id,
            "score": composite_score,
            "score_breakdown": json.dumps(score_dict),
            "label": sh_lbl,
            "trade_direction": trade_direction,
            "entry_price": sh_san["tranche_a_price"],
            "tp_price": sh_san["target_1_price"],
            "tp2_price": sh_san.get("target_2_price") or sh_san["target_1_price"],
            "sl_price": sh_san["stop_price"],
            "position_size_usd": float(sh_ladder.get("total_size_usd") or 0.0),
            "pipeline_version": pipeline_version,
            "candidate_name": candidate_name,
            "status": status,
        })

    return records


async def persist_shadow_signals(records: list[ShadowRecord]) -> int:
    """Insert shadow rows under their own pipeline_version, one transaction.

    Runs under db_write_lock via the raw connection, after the live signals
    commit — same discipline as `_persist_pending_signals`.
    """
    if not records:
        return 0

    from tpt.data.database import get_connection
    from tpt.db.write_lock import db_write_lock

    inserted = 0
    async with db_write_lock:
        async with get_connection() as conn:
            for r in records:
                await conn.execute(
                    """INSERT INTO signals
                    (scan_run_id, symbol, timestamp, score, score_breakdown, label, trade_direction,
                     entry_price, tp_price, tp2_price, sl_price, position_size_usd, status, pipeline_version)
                    VALUES (?, ?, strftime('%s', 'now'), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        r["scan_run_id"], r["symbol"], r["score"], r["score_breakdown"],
                        r["label"], r["trade_direction"], r["entry_price"], r["tp_price"],
                        r["tp2_price"], r["sl_price"], r["position_size_usd"],
                        r["status"], r["pipeline_version"],
                    ),
                )
                inserted += 1
            await conn.commit()

    if inserted:
        by_version: dict[str, int] = {}
        for r in records:
            by_version[r["pipeline_version"]] = by_version.get(r["pipeline_version"], 0) + 1
        logger.info("Recorded %d shadow signal(s): %s", inserted, by_version)
    return inserted
