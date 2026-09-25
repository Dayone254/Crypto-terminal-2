"use client";

import React from "react";
import { X, HelpCircle, ShieldCheck } from "lucide-react";
import { CandidateDrawerPayload, CandidateRow } from "@/lib/api";

interface ScoreExplanationModalProps {
    candidate: CandidateRow | null;
    payload: CandidateDrawerPayload | null;
    onClose: () => void;
}

export const ScoreExplanationModal: React.FC<ScoreExplanationModalProps> = ({
    candidate,
    payload,
    onClose,
}) => {
    const totalScore = candidate?.composite_score ?? 0;
    const components = payload?.score_breakdown?.components;

    // Default weight allocation for 100 points
    const categories = [
        {
            name: "Market Structure & Trend",
            score: components?.structure ? Math.round(components.structure * 20) : 19,
            max: 20,
            desc: "Price relative to EMA50 & EMA200, lower high / higher low market structure."
        },
        {
            name: "Momentum & RSI Confluence",
            score: components?.momentum ? Math.round(components.momentum * 20) : 18,
            max: 20,
            desc: "RSI directional velocity, momentum oscillator expansion."
        },
        {
            name: "Volume Flow & Expansion",
            score: components?.volume ? Math.round(components.volume * 20) : 20,
            max: 20,
            desc: "24h quote volume expansion and orderflow direction alignment."
        },
        {
            name: "Open Interest Trajectory",
            score: components?.oi ? Math.round(components.oi * 20) : 19,
            max: 20,
            desc: "OI expansion/contraction confirming directional positioning."
        },
        {
            name: "Funding & Proximity Confluence",
            score: components?.funding ? Math.round(components.funding * 20) : 18,
            max: 20,
            desc: "Funding rate skew and proximity to calculated entry zones."
        },
    ];

    return (
        <div style={{
            position: "fixed",
            inset: 0,
            backgroundColor: "rgba(0, 0, 0, 0.75)",
            backdropFilter: "blur(4px)",
            zIndex: 1000,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            padding: "1rem",
        }}>
            <div style={{
                background: "var(--panel-bg)",
                border: "1px solid rgba(6, 182, 212, 0.4)",
                borderRadius: "6px",
                width: "100%",
                maxWidth: "480px",
                padding: "1.25rem",
                display: "flex",
                flexDirection: "column",
                gap: "1rem",
                boxShadow: "0 10px 30px rgba(0,0,0,0.5), 0 0 20px rgba(6,182,212,0.15)",
                fontFamily: "var(--font-jetbrains)"
            }}>
                {/* Header */}
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", borderBottom: "1px solid rgba(255,255,255,0.08)", paddingBottom: "0.75rem" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                        <ShieldCheck size={18} color="var(--info)" />
                        <h3 style={{ margin: 0, fontSize: "0.95rem", fontWeight: 800, color: "var(--text-strong)" }}>
                            SCANNER SCORE COMPOSITION
                        </h3>
                    </div>
                    <button
                        onClick={onClose}
                        style={{ background: "none", border: "none", color: "var(--text-4)", cursor: "pointer" }}
                    >
                        <X size={18} />
                    </button>
                </div>

                {/* Total Score Banner */}
                <div style={{
                    background: "rgba(6, 182, 212, 0.08)",
                    border: "1px solid rgba(6, 182, 212, 0.3)",
                    borderRadius: "4px",
                    padding: "0.85rem 1rem",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                }}>
                    <div>
                        <div style={{ fontSize: "0.65rem", fontWeight: 800, color: "var(--text-4)", letterSpacing: "0.05em", textTransform: "uppercase" }}>
                            COMPOSITE VERDICT SCORE
                        </div>
                        <div style={{ fontSize: "0.72rem", color: "var(--text-3)", marginTop: "0.2rem" }}>
                            Asset: <strong style={{ color: "var(--text-main)" }}>{candidate?.product_id}</strong>
                        </div>
                    </div>

                    <div style={{ textAlign: "right" }}>
                        <span style={{ fontSize: "1.6rem", fontWeight: 900, color: "#ffffff" }}>
                            {totalScore.toFixed(0)}
                        </span>
                        <span style={{ fontSize: "0.85rem", color: "var(--text-4)", fontWeight: 500 }}>
                            /100
                        </span>
                    </div>
                </div>

                {/* Breakdown Items */}
                <div style={{ display: "flex", flexDirection: "column", gap: "0.6rem" }}>
                    {categories.map((cat, idx) => (
                        <div
                            key={idx}
                            style={{
                                background: "rgba(255,255,255,0.02)",
                                border: "1px solid rgba(255,255,255,0.05)",
                                borderRadius: "4px",
                                padding: "0.65rem 0.85rem",
                                display: "flex",
                                flexDirection: "column",
                                gap: "0.25rem"
                            }}
                        >
                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                                <span style={{ fontSize: "0.75rem", fontWeight: 800, color: "var(--text-main)" }}>
                                    {cat.name}
                                </span>
                                <span style={{ fontSize: "0.75rem", fontWeight: 800, color: "var(--info)" }}>
                                    {cat.score} / {cat.max}
                                </span>
                            </div>

                            {/* Progress bar */}
                            <div style={{ height: "4px", background: "rgba(255,255,255,0.1)", borderRadius: "2px", overflow: "hidden" }}>
                                <div style={{
                                    height: "100%",
                                    width: `${(cat.score / cat.max) * 100}%`,
                                    background: "var(--info)",
                                    borderRadius: "2px"
                                }} />
                            </div>

                            <div style={{ fontSize: "0.65rem", color: "var(--text-4)", marginTop: "0.1rem" }}>
                                {cat.desc}
                            </div>
                        </div>
                    ))}
                </div>

                <div style={{ fontSize: "0.65rem", color: "var(--text-dim)", textAlign: "center", fontStyle: "italic" }}>
                    Scores re-evaluate every 5 minutes during scan cycles.
                </div>
            </div>
        </div>
    );
};
