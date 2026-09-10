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

    return (
        <div style={{ background: "#0b0f19", border: "none", borderRadius: 0, padding: "1rem", display: "flex", flexDirection: "column", gap: "0.75rem" }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", fontSize: "0.75rem", fontWeight: 700, borderBottom: "none", paddingBottom: "0.5rem", color: "var(--text-dim)" }}>
                <span>LIMIT LADDER SETUP LEVELS</span>
                <span>LAST: <strong className="mono" style={{ color: "#FFF" }}>{fmt(lastPrice)}</strong></span>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.75rem" }}>
                {/* Entry Tranches */}
                <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                    <div style={{ background: "rgba(16, 185, 129, 0.1)", border: "none", padding: "0.6rem 0.8rem", borderRadius: 0, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                        <div>
                            <div style={{ fontWeight: 800, fontSize: "0.75rem", color: "#34D399" }}>Tranche A (60%)</div>
                            <div style={{ fontSize: "0.65rem", color: "rgba(52, 211, 153, 0.7)" }}>
                                {ladder.trade_direction === "SHORT" ? "Primary Sell Zone" : "Primary Buy Zone"}
                            </div>
                        </div>
                        <div className="mono" style={{ textAlign: "right", fontWeight: 800, color: "#FFF", fontSize: "0.95rem" }}>
                            {fmt(ladder.tranche_a_price)}
                            {distToA && (
                                <div style={{ fontSize: "0.65rem", color: "#34D399" }}>
                                    {Number(distToA) > 0 ? `+${distToA}% above` : `${distToA}% tagged`}
                                </div>
                            )}
                        </div>
                    </div>

                    <div style={{ background: "rgba(6, 182, 212, 0.1)", border: "none", padding: "0.6rem 0.8rem", borderRadius: 0, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                        <div>
                            <div style={{ fontWeight: 800, fontSize: "0.75rem", color: "#38BDF8" }}>Tranche B (40%)</div>
                            <div style={{ fontSize: "0.65rem", color: "rgba(56, 189, 248, 0.7)" }}>
                                {ladder.trade_direction === "SHORT" ? "Deep Resistance Fill" : "Deep Pocket Fill"}
                            </div>
                        </div>
                        <div className="mono" style={{ textAlign: "right", fontWeight: 800, color: "#FFF", fontSize: "0.95rem" }}>
                            {fmt(ladder.tranche_b_price)}
                        </div>
                    </div>

                    <div style={{ background: "rgba(239, 68, 68, 0.1)", border: "none", padding: "0.6rem 0.8rem", borderRadius: 0, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                        <div>
                            <div style={{ fontWeight: 800, fontSize: "0.75rem", color: "#F87171" }}>Hard Stop Loss</div>
                            <div style={{ fontSize: "0.65rem", color: "rgba(248, 113, 113, 0.7)" }}>Risk Invalidation (-3.0%)</div>
                        </div>
                        <div className="mono" style={{ textAlign: "right", fontWeight: 800, color: "#FFF", fontSize: "0.95rem" }}>
                            {fmt(ladder.stop_price)}
                        </div>
                    </div>
                </div>

                {/* Profit Targets */}
                <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                    <div style={{ background: "rgba(59, 130, 246, 0.1)", border: "none", padding: "0.6rem 0.8rem", borderRadius: 0, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                        <div>
                            <div style={{ fontWeight: 800, fontSize: "0.75rem", color: "#60A5FA" }}>Target 1 (TP1)</div>
                            <div style={{ fontSize: "0.65rem", color: "rgba(96, 165, 250, 0.7)" }}>
                                {ladder.trade_direction === "SHORT" ? "Day Low Target" : "Day High Resistance"}
                            </div>
                        </div>
                        <div className="mono" style={{ textAlign: "right", fontWeight: 800, color: "#FFF", fontSize: "0.95rem" }}>
                            {fmt(ladder.target_1_price)}
                        </div>
                    </div>

                    <div style={{ background: "rgba(139, 92, 246, 0.1)", border: "none", padding: "0.6rem 0.8rem", borderRadius: 0, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                        <div>
                            <div style={{ fontWeight: 800, fontSize: "0.75rem", color: "#C084FC" }}>Target 2 (TP2)</div>
                            <div style={{ fontSize: "0.65rem", color: "rgba(192, 132, 252, 0.7)" }}>
                                {ladder.trade_direction === "SHORT" ? "-5.0% Extension Drop" : "+5.0% Extension"}
                            </div>
                        </div>
                        <div className="mono" style={{ textAlign: "right", fontWeight: 800, color: "#FFF", fontSize: "0.95rem" }}>
                            {fmt(ladder.target_2_price)}
                        </div>
                    </div>

                    <div style={{ background: "rgba(255,255,255,0.03)", border: "none", padding: "0.6rem 0.8rem", borderRadius: 0, display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: "0.75rem", color: "var(--text-muted)" }}>
                        <span>R/R Profile:</span>
                        <span className="mono font-bold" style={{ color: "#34D399", fontWeight: 700 }}>Actionable Entry</span>
                    </div>
                </div>
            </div>
        </div>
    );
}
