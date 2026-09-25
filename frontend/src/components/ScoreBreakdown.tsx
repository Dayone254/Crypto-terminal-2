"use client";

import React from "react";
import { ScoreBreakdown as Breakdown } from "@/lib/api";

/**
 * "Why is this score what it is" — the scorer's own arithmetic, rendered.
 *
 * The persisted breakdown holds the normalised readings that fed the weighted
 * sum, which components a real observation actually backed, and the point
 * adjustments applied on top. That is enough to show the working rather than
 * assert a conclusion, which is the whole difference between this panel and the
 * prose card it sits beside.
 *
 * A component that was NOT backed is rendered as "no data", never as a neutral
 * zero — a zero-filled `0.0` and a genuine flat reading are different facts and
 * the panel must not conflate them.
 */

const COMPONENT_LABELS: Record<string, string> = {
    liquidity: "Liquidity",
    trend_strength: "Trend · 24h",
    trend_weakness: "Trend weakness · 24h",
    volatility_compression: "Volatility compression",
    volatility_expansion: "Volatility expansion",
    momentum: "Momentum · RSI 1h",
    relative_strength: "Relative strength · 7d vs BTC",
    relative_weakness: "Relative weakness · 7d vs BTC",
    l2_support: "L2 bid support",
    l2_resistance: "L2 ask resistance",
};

/** Boolean confluence flags — they gate the interaction bonuses. */
const SIGNAL_LABELS: Record<string, string> = {
    rsi_oversold: "RSI oversold",
    rsi_overbought: "RSI overbought",
    fib_confluence: "Fib confluence",
    volume_expansion: "Volume expansion",
    bb_squeeze: "Bollinger squeeze",
    trend_aligned: "Trend aligned",
};

/** Point adjustments (not normalised) that appear in `components`. */
const INTERACTION_LABELS: Record<string, string> = {
    rs_btc_bonus: "Relative-strength bonus",
    rs_btc_weakness_bonus: "Relative-weakness bonus",
    rs_btc_short_penalty: "Relative-strength penalty (short)",
    rs_btc_long_penalty: "Relative-weakness penalty (long)",
    long_squeeze_penalty: "Long-squeeze risk",
    liquidation_hunt_bonus: "Liquidation hunt",
    short_squeeze_bonus: "Short-squeeze tailwind",
    crowded_short_penalty: "Crowded-short risk",
    gamma_wall_resistance: "Dealer call wall overhead",
    gamma_wall_support: "Dealer put wall",
    gamma_wall_resistance_bounce: "Bounce off call wall",
    high_put_skew_penalty: "Put skew (fear)",
    high_put_skew_bonus: "Put skew (fear) · short tailwind",
    call_skew_greed_bonus: "Call skew (greed)",
    call_skew_greed_penalty: "Call skew (greed) · short headwind",
    macro_beta_headwind: "Macro BTC headwind",
};

const POS = "var(--pos-bright)";
const NEG = "var(--neg)";
const ABSENT = "var(--text-dim)";

function DivergentBar({ value, scale }: { value: number; scale: number }) {
    // Centred bar: fills right for positive, left for negative.
    const pct = Math.min(Math.abs(value) / scale, 1) * 50;
    const positive = value >= 0;
    return (
        <div
            style={{
                position: "relative",
                height: "4px",
                background: "rgba(255,255,255,0.06)",
                width: "100%",
                borderRadius: "2px",
                overflow: "hidden"
            }}
        >
            <div style={{ position: "absolute", left: "50%", top: 0, bottom: 0, width: "1px", background: "rgba(255,255,255,0.3)" }} />
            <div
                style={{
                    position: "absolute",
                    top: 0,
                    bottom: 0,
                    left: positive ? "50%" : `${50 - pct}%`,
                    width: `${pct}%`,
                    background: positive ? POS : NEG,
                    opacity: 0.9,
                }}
            />
        </div>
    );
}

export function ScoreBreakdownPanel({
    breakdown,
    weights,
    direction,
}: {
    breakdown: Breakdown | undefined;
    weights?: Record<string, number> | null;
    direction: string;
}) {
    if (!breakdown || !breakdown.components) {
        return (
            <div style={{ background: "var(--surface-1)", padding: "1rem", fontSize: "0.7rem", color: "var(--text-dim)" }}>
                No persisted breakdown for this setup — score written before the breakdown was recorded.
            </div>
        );
    }

    const comps = breakdown.components;
    const backed = breakdown.backed ?? {};
    const baseline = breakdown.baseline ?? 50;
    const clamped = breakdown.clamped ?? 0;
    const interactions = breakdown.interactions ?? 0;
    const weightedPoints = clamped - baseline - interactions;
    const coverage = breakdown.coverage;

    // The weighted components, in the order the active direction defines them.
    const weightMap = weights ?? {};
    const componentKeys = Object.keys(weightMap).length
        ? Object.keys(weightMap)
        : Object.keys(comps).filter((k) => k in COMPONENT_LABELS);

    const signalsFired = Object.keys(SIGNAL_LABELS).filter((k) => (comps[k] ?? 0) > 0.5);

    const interactionKeys = Object.keys(comps).filter(
        (k) => !(k in COMPONENT_LABELS) && !(k in SIGNAL_LABELS) && k !== "coverage" && k !== "tags",
    );

    const rowStyle: React.CSSProperties = {
        display: "grid",
        gridTemplateColumns: "1.15fr 42px 1fr 54px",
        alignItems: "center",
        gap: "0.5rem",
        padding: "0.22rem 0",
        fontSize: "0.68rem",
    };

    return (
        <div className="panel" style={{ padding: "var(--sp-4)", display: "flex", flexDirection: "column", gap: "var(--sp-3)" }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.5rem", flexWrap: "wrap" }}>
                <span style={{ fontSize: "0.7rem", fontWeight: 800, color: "var(--text-strong)", letterSpacing: "0.04em" }}>
                    WHY THIS SCORE
                </span>
                <span className="mono" style={{ fontSize: "0.62rem", color: "var(--text-muted)" }}>
                    {baseline.toFixed(0)} baseline {weightedPoints >= 0 ? "+" : "−"} {Math.abs(weightedPoints).toFixed(1)} weighted{" "}
                    {interactions >= 0 ? "+" : "−"} {Math.abs(interactions).toFixed(1)} adjustments ={" "}
                    <span style={{ color: "var(--text-strong)", fontWeight: 800 }}>{clamped.toFixed(1)}</span>
                </span>
            </div>

            {/* Weighted components */}
            <div style={{ display: "flex", flexDirection: "column", gap: "0.85rem", marginTop: "0.5rem" }}>
                {componentKeys.map((key) => {
                    const isBacked = backed[key] !== false;
                    const norm = comps[key] ?? 0;
                    const w = weightMap[key] ?? 0;
                    const pts = w * norm * 50;

                    if (!isBacked) {
                        return (
                            <div key={key} style={{ display: "flex", flexDirection: "column", gap: "0.25rem" }} title="No observation">
                                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", fontSize: "0.65rem", textTransform: "uppercase" }}>
                                    <span style={{ color: ABSENT }}>{COMPONENT_LABELS[key] ?? key}</span>
                                    <span className="mono" style={{ color: ABSENT }}>no data</span>
                                </div>
                                <div style={{ width: "100%", height: "4px", background: "rgba(255,255,255,0.03)", borderRadius: "2px" }} />
                            </div>
                        );
                    }

                    return (
                        <div key={key} style={{ display: "flex", flexDirection: "column", gap: "0.25rem" }}>
                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", fontSize: "0.65rem", textTransform: "uppercase" }}>
                                <span style={{ color: "var(--text-3)", fontWeight: 500 }}>{COMPONENT_LABELS[key] ?? key}</span>
                                <div style={{ textAlign: "right" }}>
                                    <span className="mono" style={{ color: "var(--text-4)", marginRight: "0.4rem", fontSize: "0.6rem" }}>W: {w.toFixed(2)}</span>
                                    <span className="mono" style={{ color: pts >= 0 ? POS : NEG, fontWeight: 700 }}>
                                        {pts >= 0 ? "+" : "−"}{Math.abs(pts).toFixed(1)}
                                    </span>
                                </div>
                            </div>
                            <DivergentBar value={norm} scale={1} />
                        </div>
                    );
                })}
            </div>

            {/* Point adjustments */}
            {interactionKeys.length > 0 && (
                <div style={{ display: "flex", flexDirection: "column", gap: "0.4rem", borderTop: "1px solid var(--line)", paddingTop: "0.75rem", marginTop: "0.5rem" }}>
                    <span style={{ fontSize: "0.6rem", color: "var(--text-4)", fontWeight: 700 }}>ADJUSTMENTS</span>
                    {interactionKeys.map((k) => {
                        const v = comps[k] ?? 0;
                        return (
                            <div key={k} style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", fontSize: "0.65rem", padding: "0.15rem 0" }}>
                                <span style={{ color: "var(--text-3)", textTransform: "uppercase", fontWeight: 500 }}>{INTERACTION_LABELS[k] ?? k}</span>
                                <span className="mono" style={{ fontWeight: 700, color: v >= 0 ? POS : NEG }}>
                                    {v >= 0 ? "+" : "−"}{Math.abs(v).toFixed(1)}
                                </span>
                            </div>
                        );
                    })}
                </div>
            )}

            {/* Signals + coverage footer */}
            <div style={{ borderTop: "1px solid rgba(255,255,255,0.06)", paddingTop: "0.5rem", display: "flex", flexDirection: "column", gap: "0.35rem" }}>
                {signalsFired.length > 0 && (
                    <div style={{ display: "flex", flexWrap: "wrap", gap: "0.3rem" }}>
                        {signalsFired.map((k) => (
                            <span key={k} className="mono" style={{ fontSize: "0.58rem", color: "var(--info)", background: "rgba(6,182,212,0.12)", padding: "0.1rem 0.35rem" }}>
                                {SIGNAL_LABELS[k]}
                            </span>
                        ))}
                    </div>
                )}
                <span style={{ fontSize: "0.62rem", color: "var(--text-dim)", lineHeight: 1.5 }}>
                    {coverage !== undefined && coverage !== null ? (
                        <>
                            Evidence backed <strong style={{ color: "var(--text-muted)" }}>{Math.round(coverage * 100)}%</strong> of the
                            model&apos;s weight. Components marked <em>no data</em> contribute nothing — the score is shrunk toward
                            neutral by exactly that shortfall, not penalised.
                        </>
                    ) : (
                        <>Coverage was not recorded for this score, so how much of the model was backed is unknown.</>
                    )}
                </span>
                {breakdown.feature_version && (
                    <span className="mono" style={{ fontSize: "0.55rem", color: "var(--text-dim)" }}>
                        feature version {breakdown.feature_version}
                    </span>
                )}
            </div>
        </div>
    );
}
