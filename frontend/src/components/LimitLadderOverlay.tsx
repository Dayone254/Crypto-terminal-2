"use client";

import React from "react";
import { CandidateLadder } from "@/lib/api";

interface LimitLadderOverlayProps {
    ladder: CandidateLadder;
    lastPrice: number;
}

export function LimitLadderOverlay({ ladder, lastPrice }: LimitLadderOverlayProps) {
    const fmt = (val: number | null | undefined) => {
        if (val === null || val === undefined) return "N/A";
        return val < 1 ? `$${val.toFixed(5)}` : `$${val.toFixed(2)}`;
    };

    const distToA = ladder.tranche_a_price
        ? (((lastPrice - ladder.tranche_a_price) / ladder.tranche_a_price) * 100).toFixed(1)
        : null;

    // These were hardcoded ("Tranche A (60%)", "Risk Invalidation (-3.0%)", "-5.0%
    // Extension Drop") while the ladder sizes and stop distance are dynamic — so the
    // panel contradicted the header, which showed 70/30 and the 5% risk clamp.
    const aPct = Math.round(ladder.tranche_a_size_pct ?? 60);
    const bPct = Math.round(ladder.tranche_b_size_pct ?? 40);
    const isShort = ladder.trade_direction === "SHORT";
    const pctMove = (from: number | null | undefined, to: number | null | undefined) =>
        from && to ? Math.abs(((to - from) / from) * 100) : null;
    const stopPct = pctMove(ladder.tranche_a_price, ladder.stop_price);
    const t2Pct = pctMove(ladder.tranche_a_price, ladder.target_2_price);

    return (
        <div style={{ display: "flex", flexDirection: "column" }}>
            <div style={{ display: "flex", justifyContent: "space-between", borderBottom: "1px solid var(--line-heavy)", paddingBottom: "0.25rem", marginBottom: "0.25rem", fontSize: "0.65rem", color: "var(--text-4)", fontWeight: 700 }}>
                <span>LIMIT LADDER</span>
                <span>LAST: {fmt(lastPrice)}</span>
            </div>

            <div style={{ display: "flex", flexDirection: "column", fontSize: "0.7rem" }}>
                {/* TRANCHE A */}
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", padding: "0.15rem 0.25rem", background: "rgba(255,255,255,0.015)", borderBottom: "1px solid var(--line)" }}>
                    <div style={{ display: "flex", gap: "0.5rem", alignItems: "baseline" }}>
                        <span style={{ color: "var(--text-3)", fontWeight: 500 }}>TRANCHE A ({aPct}%)</span>
                        <span style={{ fontSize: "0.55rem", color: "var(--text-5)" }}>{ladder.trade_direction === "SHORT" ? "SELL ZONE" : "BUY ZONE"}</span>
                    </div>
                    <div style={{ textAlign: "right" }}>
                        <span className="mono" style={{ color: "var(--text-main)", fontWeight: 700, fontSize: "0.75rem" }}>{fmt(ladder.tranche_a_price)}</span>
                        {distToA && (
                            <span style={{ fontSize: "0.6rem", color: "var(--text-4)", marginLeft: "0.5rem" }}>({Number(distToA) > 0 ? `+${distToA}%` : `${distToA}%`})</span>
                        )}
                    </div>
                </div>

                {/* TRANCHE B */}
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", padding: "0.15rem 0.25rem", borderBottom: "1px solid var(--line)" }}>
                    <div style={{ display: "flex", gap: "0.5rem", alignItems: "baseline" }}>
                        <span style={{ color: "var(--text-3)", fontWeight: 500 }}>TRANCHE B ({bPct}%)</span>
                        <span style={{ fontSize: "0.55rem", color: "var(--text-5)" }}>DEEP FILL</span>
                    </div>
                    <span className="mono" style={{ color: "var(--text-main)", fontWeight: 700, fontSize: "0.75rem" }}>{fmt(ladder.tranche_b_price)}</span>
                </div>

                {/* HARD STOP */}
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", padding: "0.15rem 0.25rem", background: "rgba(255,255,255,0.015)", borderBottom: "1px solid var(--line-heavy)" }}>
                    <div style={{ display: "flex", gap: "0.5rem", alignItems: "baseline" }}>
                        <span style={{ color: "var(--text-3)", fontWeight: 500 }}>HARD STOP</span>
                    </div>
                    <div style={{ textAlign: "right" }}>
                        <span className="mono" style={{ color: "var(--neg-bright)", fontWeight: 700, fontSize: "0.75rem" }}>{fmt(ladder.stop_price)}</span>
                        {stopPct !== null && (
                            <span style={{ fontSize: "0.6rem", color: "var(--neg)", marginLeft: "0.5rem" }}>(-{stopPct.toFixed(1)}%)</span>
                        )}
                    </div>
                </div>

                {/* TARGET 1 */}
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", padding: "0.15rem 0.25rem", borderBottom: "1px solid var(--line)" }}>
                    <span style={{ color: "var(--text-3)", fontWeight: 500 }}>TARGET 1</span>
                    <span className="mono" style={{ color: "var(--accent-blue-bright)", fontWeight: 700, fontSize: "0.75rem" }}>{fmt(ladder.target_1_price)}</span>
                </div>

                {/* TARGET 2 */}
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", padding: "0.15rem 0.25rem", background: "rgba(255,255,255,0.015)", borderBottom: "1px solid var(--line)" }}>
                    <span style={{ color: "var(--text-3)", fontWeight: 500 }}>TARGET 2</span>
                    <div style={{ textAlign: "right" }}>
                        <span className="mono" style={{ color: "var(--accent-purple-bright)", fontWeight: 700, fontSize: "0.75rem" }}>{fmt(ladder.target_2_price)}</span>
                        {t2Pct !== null && (
                            <span style={{ fontSize: "0.6rem", color: "var(--accent-purple)", marginLeft: "0.5rem" }}>({isShort ? "-" : "+"}{t2Pct.toFixed(1)}%)</span>
                        )}
                    </div>
                </div>

                {/* R/R */}
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", padding: "0.15rem 0.25rem" }}>
                    <span style={{ color: "var(--text-4)", fontWeight: 500 }}>R/R RATIO</span>
                    <span className="mono" style={{ color: "var(--text-main)", fontWeight: 700, fontSize: "0.7rem" }}>
                        {ladder.rr_a_t1 !== undefined && ladder.rr_a_t2 !== undefined
                            ? `${ladder.rr_a_t1.toFixed(2)} → ${ladder.rr_a_t2.toFixed(2)}`
                            : "—"}
                    </span>
                </div>
            </div>
        </div>
    );
}
