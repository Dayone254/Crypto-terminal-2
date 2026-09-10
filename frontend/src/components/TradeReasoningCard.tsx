"use client";

import React from "react";
import { CandidateRow } from "@/lib/api";
import { Activity, BarChart2, Brain, CheckCircle2, Layers, Zap } from "lucide-react";

interface TradeReasoningCardProps {
    candidate: CandidateRow;
}

export function TradeReasoningCard({ candidate }: TradeReasoningCardProps) {
    const isCoiled = candidate.label === "COILED";
    const isEntry = candidate.label === "ENTRY_ZONE";
    const isEarly = candidate.label === "EARLY";

    const getTradeThesis = () => {
        const l2Buy = candidate.tags?.includes("L2_BUY_WALL_SUPPORT");
        const l2Sell = candidate.tags?.includes("L2_SELL_WALL_REJECTION");
        let l2Str = "";
        if (l2Buy) l2Str = " Technicals align with a deep pocket >$100k institutional bid resting nearby.";
        else if (l2Sell) l2Str = " However, overhead supply >$100k presents a severe breakout constraint (L2 Resistance).";

        if (isEntry) {
            return `${candidate.product_id} has entered the optimal limit-ladder buy zone. Price is interacting with key volume support while composite setup score is strong (${candidate.composite_score.toFixed(0)}/100). Position-in-range (PIR: ${candidate.pos_in_range.toFixed(2)}) indicates high probability reward-to-risk ratio.${l2Str}`;
        }
        if (isCoiled) {
            return `${candidate.product_id} is in a highly compressed coiled state (RSI < 45 on 1h) near key Fibonacci/VWAP support. Coiled setups represent low-volatility compression prior to directional expansion. Entry limits are set to capture the breakout build-up.${l2Str}`;
        }
        if (isEarly) {
            return `${candidate.product_id} exhibits early structural strength with solid quote volume ($${(candidate.quote_vol_24h / 1_000_000).toFixed(2)}M). Structure score is leading momentum, providing early entry prior to retail chase phase.${l2Str}`;
        }
        return `${candidate.product_id} is on active watch. Setup score is ${candidate.composite_score.toFixed(0)}/100. Key levels are monitored for entry qualification.`;
    };

    return (
        <div style={{ background: "#0b0f19", border: "none", borderRadius: 0, padding: "1.25rem", display: "flex", flexDirection: "column", gap: "1rem" }}>
            {/* Header */}
            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", borderBottom: "none", paddingBottom: "0.75rem" }}>
                <Brain size={18} color="var(--accent-emerald)" />
                <span style={{ fontWeight: 800, fontSize: "0.9rem", color: "#FFF" }}>TRADE REASONING & SETUP THESIS</span>
            </div>

            {/* Why Trade Was Taken Card */}
            <div style={{ background: "rgba(16, 185, 129, 0.1)", border: "none", borderRadius: 0, padding: "0.85rem", display: "flex", flexDirection: "column", gap: "0.4rem" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "0.4rem", color: "#34D399", fontWeight: 800, fontSize: "0.8rem" }}>
                    <CheckCircle2 size={16} />
                    <span>WHY THIS SETUP WAS IDENTIFIED</span>
                </div>
                <p style={{ color: "#E2E8F0", fontSize: "0.75rem", lineHeight: 1.6, margin: 0 }}>
                    {getTradeThesis()}
                </p>
            </div>

            {/* Confluence Factor Grid */}
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.75rem" }}>
                <div style={{ background: "rgba(0,0,0,0.4)", border: "none", borderRadius: 0, padding: "0.6rem 0.8rem" }}>
                    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", color: "var(--text-muted)", fontSize: "0.65rem" }}>
                        <span style={{ display: "flex", alignItems: "center", gap: "0.3rem" }}><Layers size={12} color="var(--accent-cyan)" /> Structure</span>
                        <span style={{ color: "#34D399", fontWeight: 800 }}>Strong</span>
                    </div>
                    <div style={{ color: "#FFF", fontWeight: 700, fontSize: "0.8rem", marginTop: "0.2rem" }}>Fib 78.6% & VWAP Confluence</div>
                </div>

                <div style={{ background: "rgba(0,0,0,0.4)", border: "none", borderRadius: 0, padding: "0.6rem 0.8rem" }}>
                    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", color: "var(--text-muted)", fontSize: "0.65rem" }}>
                        <span style={{ display: "flex", alignItems: "center", gap: "0.3rem" }}><Activity size={12} color="var(--accent-purple)" /> Momentum</span>
                        <span style={{ color: "#C084FC", fontWeight: 800 }}>Coiled</span>
                    </div>
                    <div style={{ color: "#FFF", fontWeight: 700, fontSize: "0.8rem", marginTop: "0.2rem" }}>Wilder RSI 1h Compression</div>
                </div>

                <div style={{ background: "rgba(0,0,0,0.4)", border: "none", borderRadius: 0, padding: "0.6rem 0.8rem" }}>
                    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", color: "var(--text-muted)", fontSize: "0.65rem" }}>
                        <span style={{ display: "flex", alignItems: "center", gap: "0.3rem" }}><BarChart2 size={12} color="var(--accent-blue)" /> 24h Volume</span>
                        <span style={{ color: "#60A5FA", fontWeight: 800 }}>Liquid</span>
                    </div>
                    <div style={{ color: "#FFF", fontWeight: 700, fontSize: "0.8rem", marginTop: "0.2rem" }}>${(candidate.quote_vol_24h / 1_000_000).toFixed(2)}M Quote Vol</div>
                </div>

                <div style={{ background: "rgba(0,0,0,0.4)", border: "none", borderRadius: 0, padding: "0.6rem 0.8rem" }}>
                    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", color: "var(--text-muted)", fontSize: "0.65rem" }}>
                        <span style={{ display: "flex", alignItems: "center", gap: "0.3rem" }}><Zap size={12} color="var(--accent-amber)" /> Range Position</span>
                        <span style={{ color: "#FBBF24", fontWeight: 800 }}>PIR: {candidate.pos_in_range.toFixed(2)}</span>
                    </div>
                    <div style={{ color: "#FFF", fontWeight: 700, fontSize: "0.8rem", marginTop: "0.2rem" }}>Discounted Range Zone</div>
                </div>
            </div>

            {/* Tags / Confluence Badges */}
            {candidate.tags && candidate.tags.length > 0 && (
                <div>
                    <span style={{ fontSize: "0.65rem", color: "var(--text-dim)", fontWeight: 700, textTransform: "uppercase", display: "block", marginBottom: "0.4rem" }}>
                        Active Technical Confluence Badges
                    </span>
                    <div style={{ display: "flex", flexWrap: "wrap", gap: "0.4rem" }}>
                        {candidate.tags.map((tag) => (
                            <span
                                key={tag}
                                className="mono"
                                style={{
                                    padding: "0.2rem 0.5rem",
                                    borderRadius: 0,
                                    background: "rgba(6,182,212,0.15)",
                                    border: "none",
                                    color: "var(--accent-cyan)",
                                    fontWeight: 800,
                                    fontSize: "0.7rem",
                                }}
                            >
                                #{tag}
                            </span>
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
}
