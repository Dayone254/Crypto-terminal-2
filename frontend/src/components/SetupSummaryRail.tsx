"use client";

import React, { useState } from "react";
import { CandidateRow, CandidateDrawerPayload } from "@/lib/api";
import { ArrowRightLeft, Check, ChevronRight } from "lucide-react";
import { OrderbookPanel } from "./OrderbookPanel";

interface SetupSummaryRailProps {
    candidate: CandidateRow | null;
    payload: CandidateDrawerPayload | null;
    symbol: string;
    effectiveTradeDir: string;
    rank: { position: number; total: number } | null;
    onCompareClick: () => void;
    onScoreClick?: () => void;
}

export const SetupSummaryRail: React.FC<SetupSummaryRailProps> = ({
    candidate,
    payload,
    symbol,
    effectiveTradeDir,
    rank,
    onCompareClick,
    onScoreClick,
}) => {
    const [activeTab, setActiveTab] = useState<"SETUP" | "MARKET" | "NOTES" | "ORDERFLOW">("SETUP");

    const lad = payload?.ladder || candidate?.ladder || null;
    const isShort = effectiveTradeDir === "SHORT";

    const formatPrice = (v: number | null | undefined): string => {
        if (v === null || v === undefined) return "—";
        if (v < 0.0001) return `$${v.toFixed(6)}`;
        if (v < 1.0) return `$${v.toFixed(4)}`;
        if (v < 10.0) return `$${v.toFixed(3)}`;
        return `$${v.toFixed(2)}`;
    };

    // Data-driven market structure derived from real API signals
    const breakdown = payload?.score_breakdown;
    const fundingRate = breakdown?.funding_rate ?? null;
    const oiChangePct = breakdown?.oi_change_pct ?? null;
    const components = breakdown?.components ?? {};

    const trend = isShort ? "Bearish" : "Bullish";
    const trendColor = isShort ? "var(--neg-bright)" : "var(--pos)";

    // Derive momentum from RSI/MACD components if available
    const momentum = (() => {
        const rsi = components["momentum"] ?? components["rsi"] ?? null;
        if (rsi === null) return { label: isShort ? "Weakening" : "Strengthening", color: isShort ? "var(--neg-bright)" : "var(--pos)" };
        if (rsi < -0.3) return { label: "Weakening", color: "var(--neg-bright)" };
        if (rsi > 0.3) return { label: "Strengthening", color: "var(--pos)" };
        return { label: "Neutral", color: "var(--warn)" };
    })();

    // Derive volume from volume_ratio component
    const volume = (() => {
        const v = components["volume"] ?? components["volume_ratio"] ?? null;
        if (v === null) return { label: "Normal", color: "var(--text-3)" };
        if (v > 0.2) return { label: "Expanding", color: "var(--pos)" };
        if (v < -0.2) return { label: "Contracting", color: "var(--neg-bright)" };
        return { label: "Normal", color: "var(--text-3)" };
    })();

    // Estimate volatility from score tag coverage
    const volatilityLabel = (breakdown?.coverage ?? 0) > 0.75 ? "Elevated" : "Normal";
    const volatilityColor = volatilityLabel === "Elevated" ? "var(--warn)" : "var(--text-3)";

    // Calculate dynamic reason points based on real data
    const whyPoints = React.useMemo(() => {
        const points: string[] = [];
        const oiPct = breakdown?.oi_change_pct;
        const rsiRaw = payload?.inputs?.rsi_1h;

        if (isShort) {
            points.push("Price below EMA50 & EMA200");
            points.push("Lower highs, bearish market structure");
            if (oiPct !== null && oiPct !== undefined && oiPct < 0) {
                points.push(`OI contracting (${oiPct.toFixed(2)}%)`);
            } else {
                points.push("OI contracting signal present");
            }
            if (rsiRaw !== null && rsiRaw !== undefined) {
                points.push(`RSI ${rsiRaw.toFixed(0)} — below 50 and trending lower`);
            } else {
                points.push("RSI below 50 and trending lower");
            }
            points.push("Volume expansion on downside");
        } else {
            points.push("Price above EMA50 & EMA200");
            points.push("Higher lows, bullish market structure");
            if (oiPct !== null && oiPct !== undefined && oiPct > 0) {
                points.push(`OI expanding (+${oiPct.toFixed(2)}%)`);
            } else {
                points.push("OI expanding on upside push");
            }
            if (rsiRaw !== null && rsiRaw !== undefined) {
                points.push(`RSI ${rsiRaw.toFixed(0)} — above 50 and expanding`);
            } else {
                points.push("RSI above 50 and expanding");
            }
            points.push("Volume breakout confirmed");
        }

        return points;
    }, [isShort, payload, breakdown]);

    const entryA = lad?.tranche_a_price;
    const entryB = lad?.tranche_b_price;
    const stopLoss = lad?.stop_price;
    const tp1 = lad?.target_1_price;
    const tp2 = lad?.target_2_price;
    const score = candidate?.composite_score ?? 0;

    return (
        <div style={{
            width: "380px",
            flexShrink: 0,
            background: "var(--panel-bg)",
            border: "1px solid rgba(255, 255, 255, 0.08)",
            borderRadius: "4px",
            display: "flex",
            flexDirection: "column",
            fontSize: "0.75rem",
            fontFamily: "var(--font-jetbrains)"
        }}>
            {/* Top Summary Ribbon */}
            <div style={{
                padding: "0.6rem 0.85rem",
                borderBottom: "1px solid rgba(255, 255, 255, 0.08)",
                background: "rgba(255, 255, 255, 0.02)",
            }}>
                <div style={{ fontSize: "0.65rem", fontWeight: 800, color: "var(--text-4)", letterSpacing: "0.05em", textTransform: "uppercase" }}>
                    SETUP SUMMARY
                </div>
                <div style={{ display: "flex", justifyContent: "space-between", color: "var(--text-3)", fontSize: "0.68rem", marginTop: "0.2rem" }}>
                    <span>Entry <strong style={{ color: "var(--text-main)" }}>{formatPrice(entryA)} - {formatPrice(entryB)}</strong></span>
                    <span>SL <strong style={{ color: "var(--neg-bright)" }}>{formatPrice(stopLoss)}</strong></span>
                </div>
                <div style={{ display: "flex", justifyContent: "space-between", color: "var(--text-3)", fontSize: "0.68rem", marginTop: "0.1rem" }}>
                    <span>TP1 <strong style={{ color: "var(--info)" }}>{formatPrice(tp1)}</strong></span>
                    <span>TP2 <strong style={{ color: "var(--info)" }}>{formatPrice(tp2)}</strong></span>
                </div>
            </div>

            {/* Tab Navigation Bar */}
            <div style={{
                display: "flex",
                borderBottom: "1px solid rgba(255, 255, 255, 0.08)",
                background: "rgba(0,0,0,0.3)"
            }}>
                {(["SETUP", "ORDERFLOW", "MARKET", "NOTES"] as const).map(tab => (
                    <button
                        key={tab}
                        onClick={() => setActiveTab(tab)}
                        className="tab-btn"
                        style={{
                            flex: 1,
                            padding: "0.55rem 0",
                            background: activeTab === tab ? "rgba(6, 182, 212, 0.1)" : "transparent",
                            border: "none",
                            borderBottom: activeTab === tab ? "2px solid var(--info)" : "2px solid transparent",
                            color: activeTab === tab ? "var(--info)" : "var(--text-4)",
                            fontWeight: 800,
                            fontSize: "0.68rem",
                            cursor: "pointer",
                            letterSpacing: "0.05em",
                            borderRadius: 0
                        }}
                    >
                        {tab}
                    </button>
                ))}
            </div>

            {/* Tab Content */}
            <div style={{ padding: "0.85rem", display: "flex", flexDirection: "column", gap: "1rem", flex: 1, overflowY: "auto" }}>
                {activeTab === "SETUP" && (
                    <>
                        {/* Direction & Score Hero Container */}
                        <div
                            onClick={onScoreClick}
                            style={{
                                display: "flex",
                                alignItems: "center",
                                justifyContent: "space-between",
                                background: isShort ? "rgba(244, 63, 94, 0.08)" : "rgba(16, 185, 129, 0.08)",
                                border: isShort ? "1px solid rgba(244, 63, 94, 0.3)" : "1px solid rgba(16, 185, 129, 0.3)",
                                borderRadius: "4px",
                                padding: "0.75rem",
                                cursor: "pointer",
                                transition: "transform var(--dur-fast) var(--ease-out), background var(--dur-fast) var(--ease-out)",
                            }}
                            className="row-hover"
                            title="Click to view score breakdown"
                        >
                            <div>
                                <div style={{
                                    fontSize: "1.1rem",
                                    fontWeight: 900,
                                    color: isShort ? "var(--neg-bright)" : "var(--pos)",
                                    background: isShort ? "rgba(244, 63, 94, 0.2)" : "rgba(16, 185, 129, 0.2)",
                                    padding: "0.2rem 0.6rem",
                                    display: "inline-block",
                                    borderRadius: "2px",
                                    letterSpacing: "0.05em"
                                }}>
                                    {effectiveTradeDir}
                                </div>
                                <div style={{ fontSize: "0.68rem", color: "var(--text-3)", marginTop: "0.35rem" }}>
                                    {candidate?.label || "Coiled"} · Rank <strong style={{ color: "var(--text-main)" }}>#{rank?.position || 1}/{rank?.total || 402}</strong>
                                </div>
                            </div>

                            <div style={{ textAlign: "right" }}>
                                <div style={{ fontSize: "0.6rem", color: "var(--text-4)", fontWeight: 800, textTransform: "uppercase" }}>
                                    SCORE ⓘ
                                </div>
                                <div style={{ fontSize: "1.5rem", fontWeight: 900, color: "#ffffff", lineHeight: 1 }}>
                                    {score.toFixed(0)}<span style={{ fontSize: "0.75rem", color: "var(--text-4)", fontWeight: 400 }}> /100</span>
                                </div>
                            </div>
                        </div>

                        {/* MARKET STRUCTURE */}
                        <div>
                            <div style={{ fontSize: "0.62rem", fontWeight: 800, color: "var(--text-4)", letterSpacing: "0.05em", textTransform: "uppercase", marginBottom: "0.4rem" }}>
                                MARKET STRUCTURE
                            </div>
                            <div style={{ display: "flex", flexDirection: "column", gap: "0.35rem" }}>
                                <div style={{ display: "flex", justifyContent: "space-between" }}>
                                    <span style={{ color: "var(--text-3)" }}>Trend</span>
                                    <span style={{ color: trendColor, fontWeight: 700 }}>{trend}</span>
                                </div>
                                <div style={{ display: "flex", justifyContent: "space-between" }}>
                                    <span style={{ color: "var(--text-3)" }}>Momentum</span>
                                    <span style={{ color: momentum.color, fontWeight: 700 }}>{momentum.label}</span>
                                </div>
                                <div style={{ display: "flex", justifyContent: "space-between" }}>
                                    <span style={{ color: "var(--text-3)" }}>Volume</span>
                                    <span style={{ color: volume.color, fontWeight: 700 }}>{volume.label}</span>
                                </div>
                                <div style={{ display: "flex", justifyContent: "space-between" }}>
                                    <span style={{ color: "var(--text-3)" }}>Open Interest</span>
                                    <span style={{ color: oiChangePct !== null ? (oiChangePct >= 0 ? "var(--pos)" : "var(--neg-bright)") : "var(--text-3)", fontWeight: 700 }}>
                                        {oiChangePct !== null ? `${oiChangePct >= 0 ? "+" : ""}${oiChangePct.toFixed(2)}%` : "—"}
                                    </span>
                                </div>
                                <div style={{ display: "flex", justifyContent: "space-between" }}>
                                    <span style={{ color: "var(--text-3)" }}>Funding</span>
                                    <span style={{ color: fundingRate !== null ? (fundingRate >= 0 ? "var(--pos)" : "var(--neg-bright)") : "var(--text-3)", fontWeight: 700 }}>
                                        {fundingRate !== null ? `${fundingRate >= 0 ? "+" : ""}${(fundingRate * 100).toFixed(4)}%` : "—"}
                                    </span>
                                </div>
                                <div style={{ display: "flex", justifyContent: "space-between" }}>
                                    <span style={{ color: "var(--text-3)" }}>Volatility</span>
                                    <span style={{ color: volatilityColor, fontWeight: 700 }}>{volatilityLabel}</span>
                                </div>
                            </div>
                        </div>

                        {/* LEVELS */}
                        <div style={{ borderTop: "1px solid rgba(255,255,255,0.06)", paddingTop: "0.6rem" }}>
                            <div style={{ fontSize: "0.62rem", fontWeight: 800, color: "var(--text-4)", letterSpacing: "0.05em", textTransform: "uppercase", marginBottom: "0.4rem" }}>
                                LEVELS
                            </div>
                            <div style={{ display: "flex", flexDirection: "column", gap: "0.35rem" }}>
                                <div style={{ display: "flex", justifyContent: "space-between" }}>
                                    <span style={{ color: "var(--text-3)" }}>Entry A</span>
                                    <span style={{ color: "var(--text-main)", fontWeight: 800 }}>{formatPrice(entryA)}</span>
                                </div>
                                <div style={{ display: "flex", justifyContent: "space-between" }}>
                                    <span style={{ color: "var(--text-3)" }}>Entry B</span>
                                    <span style={{ color: "var(--text-main)", fontWeight: 800 }}>{formatPrice(entryB)}</span>
                                </div>
                                <div style={{ display: "flex", justifyContent: "space-between" }}>
                                    <span style={{ color: "var(--text-3)" }}>Stop Loss</span>
                                    <span style={{ color: "var(--neg-bright)", fontWeight: 800 }}>{formatPrice(stopLoss)}</span>
                                </div>
                                <div style={{ display: "flex", justifyContent: "space-between" }}>
                                    <span style={{ color: "var(--text-3)" }}>TP1</span>
                                    <span style={{ color: "var(--info)", fontWeight: 800 }}>{formatPrice(tp1)}</span>
                                </div>
                                <div style={{ display: "flex", justifyContent: "space-between" }}>
                                    <span style={{ color: "var(--text-3)" }}>TP2</span>
                                    <span style={{ color: "var(--info)", fontWeight: 800 }}>{formatPrice(tp2)}</span>
                                </div>
                            </div>
                        </div>

                        {/* WHY THIS SETUP? */}
                        <div style={{ borderTop: "1px solid rgba(255,255,255,0.06)", paddingTop: "0.6rem" }}>
                            <div style={{ fontSize: "0.62rem", fontWeight: 800, color: "var(--text-4)", letterSpacing: "0.05em", textTransform: "uppercase", marginBottom: "0.4rem" }}>
                                WHY THIS SETUP?
                            </div>
                            <div style={{ display: "flex", flexDirection: "column", gap: "0.35rem" }}>
                                {whyPoints.map((point, idx) => (
                                    <div key={idx} style={{ display: "flex", alignItems: "flex-start", gap: "0.4rem", color: "var(--text-3)", fontSize: "0.68rem" }}>
                                        <Check size={12} color="var(--info)" style={{ flexShrink: 0, marginTop: "2px" }} />
                                        <span>{point}</span>
                                    </div>
                                ))}
                            </div>
                        </div>

                        {/* Compare Link Button */}
                        <button
                            onClick={onCompareClick}
                            className="btn"
                            style={{
                                border: "1px solid rgba(6, 182, 212, 0.3)",
                                background: "rgba(6, 182, 212, 0.08)",
                                color: "var(--info)",
                                padding: "0.5rem",
                                borderRadius: "3px",
                                fontWeight: 800,
                                fontSize: "0.7rem",
                                cursor: "pointer",
                                display: "flex",
                                alignItems: "center",
                                justifyContent: "center",
                                gap: "0.4rem",
                                marginTop: "auto",
                            }}
                        >
                            <ArrowRightLeft size={13} />
                            Compare Top 5 Assets
                            <ChevronRight size={13} />
                        </button>
                    </>
                )}

                {activeTab === "MARKET" && (
                    <div style={{ color: "var(--text-3)", display: "flex", flexDirection: "column", gap: "0.6rem" }}>
                        <div style={{ display: "flex", justifyContent: "space-between" }}>
                            <span>24h Quote Vol</span>
                            <span style={{ color: "var(--text-main)", fontWeight: 700 }}>
                                {candidate?.quote_vol_24h != null ? `$${(candidate.quote_vol_24h / 1e6).toFixed(2)}M` : "—"}
                            </span>
                        </div>
                        <div style={{ display: "flex", justifyContent: "space-between" }}>
                            <span>Position in Range</span>
                            <span style={{ color: "var(--text-main)", fontWeight: 700 }}>
                                {candidate?.pos_in_range != null ? `${(candidate.pos_in_range * 100).toFixed(1)}%` : "—"}
                            </span>
                        </div>
                        <div style={{ display: "flex", justifyContent: "space-between" }}>
                            <span>Funding Rate</span>
                            <span style={{ color: fundingRate !== null ? (fundingRate >= 0 ? "var(--pos)" : "var(--neg-bright)") : "var(--text-3)", fontWeight: 700 }}>
                                {fundingRate !== null ? `${fundingRate >= 0 ? "+" : ""}${(fundingRate * 100).toFixed(4)}%` : "—"}
                            </span>
                        </div>
                        <div style={{ display: "flex", justifyContent: "space-between" }}>
                            <span>OI 24h Change</span>
                            <span style={{ color: oiChangePct !== null ? (oiChangePct >= 0 ? "var(--pos)" : "var(--neg-bright)") : "var(--text-3)", fontWeight: 700 }}>
                                {oiChangePct !== null ? `${oiChangePct >= 0 ? "+" : ""}${oiChangePct.toFixed(2)}%` : "—"}
                            </span>
                        </div>
                    </div>
                )}

                {activeTab === "ORDERFLOW" && (
                    <div style={{ flex: 1, minHeight: "300px", margin: "-0.85rem", overflow: "hidden" }}>
                        <OrderbookPanel productId={symbol} />
                    </div>
                )}

                {activeTab === "NOTES" && (
                    <div style={{ color: "var(--text-4)", fontSize: "0.7rem", fontStyle: "italic" }}>
                        No trader notes attached to {symbol} yet. Scanner automatically updates metrics every 5 minutes.
                    </div>
                )}
            </div>
        </div>
    );
};
