"use client";

import React, { useState } from "react";
import { CandidateDrawerPayload, CandidateRow, ScoringWeightsConfig } from "@/lib/api";
import { SetupCalculator } from "@/components/SetupCalculator";
import { LimitLadderOverlay } from "@/components/LimitLadderOverlay";
import { TradeReasoningCard } from "@/components/TradeReasoningCard";
import { ScoreBreakdownPanel } from "@/components/ScoreBreakdown";
import { Level2Depth } from "@/components/Level2Depth";
import { GammaEngineVisualizer } from "@/components/GammaEngineVisualizer";
import { Activity, Calculator, Layers, Sliders, Target } from "lucide-react";

interface DeepAnalyticalToolsDrawerProps {
    symbol: string;
    lastPrice: number;
    ladder: any;
    payload: CandidateDrawerPayload | null;
    candidate: CandidateRow | null;
    scoring: ScoringWeightsConfig | null;
    effectiveTradeDir: string;
    rank: { position: number; total: number } | null;
}

export const DeepAnalyticalToolsDrawer: React.FC<DeepAnalyticalToolsDrawerProps> = ({
    symbol,
    lastPrice,
    ladder,
    payload,
    candidate,
    scoring,
    effectiveTradeDir,
    rank,
}) => {
    const [activeTool, setActiveTool] = useState<"CALCULATOR" | "LADDER" | "GAMMA" | "L2" | "BREAKDOWN">("CALCULATOR");

    return (
        <div style={{
            marginTop: "1rem",
            display: "flex",
            flexDirection: "column",
            gap: "0"
        }}>
            {/* Tool Selector Tab Bar */}
            <div style={{
                display: "flex",
                gap: "1.5rem",
                borderBottom: "1px solid var(--line-heavy)",
                paddingBottom: "0",
                overflowX: "auto"
            }}>
                {[
                    { id: "CALCULATOR", label: "TRADE CALCULATOR", icon: Calculator },
                    { id: "LADDER", label: "LIMIT LADDER", icon: Target },
                    { id: "GAMMA", label: "GAMMA ENGINE", icon: Activity },
                    { id: "L2", label: "L2 DEPTH", icon: Sliders },
                    { id: "BREAKDOWN", label: "SCORE BREAKDOWN", icon: Layers },
                ].map((t) => {
                    const Icon = t.icon;
                    const isActive = activeTool === t.id;
                    return (
                        <button
                            key={t.id}
                            onClick={() => setActiveTool(t.id as any)}
                            style={{
                                display: "inline-flex",
                                alignItems: "center",
                                gap: "0.35rem",
                                padding: "0.25rem 0.1rem 0.5rem 0.1rem",
                                background: "transparent",
                                border: "none",
                                borderBottom: isActive ? "2px solid var(--info)" : "2px solid transparent",
                                color: isActive ? "var(--text-main)" : "var(--text-3)",
                                fontWeight: isActive ? 800 : 500,
                                fontSize: "0.68rem",
                                cursor: "pointer",
                                fontFamily: "var(--font-jetbrains)",
                                textTransform: "uppercase",
                                letterSpacing: "0.03em"
                            }}
                        >
                            <Icon size={12} color={isActive ? "var(--info)" : "inherit"} />
                            {t.label}
                        </button>
                    );
                })}
            </div>

            {/* Content View */}
            <div style={{ paddingTop: "1rem" }}>
                {activeTool === "CALCULATOR" && (
                    <SetupCalculator symbol={symbol} lastPrice={lastPrice} ladder={ladder || null} />
                )}

                {activeTool === "LADDER" && (
                    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
                        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                            <Target size={18} color="var(--info)" />
                            <h3 style={{ fontSize: "0.85rem", fontWeight: 800, color: "var(--text-strong)", letterSpacing: "0.03em" }}>
                                LIMIT LADDER TARGET MATRIX
                            </h3>
                        </div>
                        {ladder ? (
                            <LimitLadderOverlay ladder={ladder} lastPrice={lastPrice} />
                        ) : (
                            <div className="empty-state">
                                <span>No ladder was computed for this setup.</span>
                            </div>
                        )}
                    </div>
                )}

                {activeTool === "GAMMA" && (
                    <GammaEngineVisualizer symbol={symbol} />
                )}

                {activeTool === "L2" && (
                    <Level2Depth symbol={symbol} />
                )}

                {activeTool === "BREAKDOWN" && (
                    <div style={{ display: "flex", gap: "1rem", flexWrap: "wrap" }}>
                        {candidate && (
                            <div style={{ flex: 1, minWidth: "300px" }}>
                                <TradeReasoningCard
                                    candidate={candidate}
                                    inputs={payload?.inputs}
                                    components={payload?.score_breakdown?.components}
                                    coverage={payload?.coverage ?? candidate.coverage}
                                    direction={effectiveTradeDir}
                                    rank={rank}
                                />
                            </div>
                        )}

                        {candidate && (
                            <div style={{ flex: 1, minWidth: "300px" }}>
                                <ScoreBreakdownPanel
                                    breakdown={payload?.score_breakdown}
                                    weights={effectiveTradeDir === "SHORT" ? scoring?.component_weights.SHORT : scoring?.component_weights.LONG}
                                    direction={effectiveTradeDir}
                                />
                            </div>
                        )}
                    </div>
                )}
            </div>
        </div>
    );
};
