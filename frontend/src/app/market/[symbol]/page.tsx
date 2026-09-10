"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import dynamic from "next/dynamic";
import { CandidateDrawerPayload, CandidateRow, HistoricalSetup, fetchCandidates, fetchMarketLadder, fetchMarketTradeHistory, pinSymbol, unpinSymbol } from "@/lib/api";
import { LimitLadderOverlay } from "@/components/LimitLadderOverlay";
import { SetupCalculator } from "@/components/SetupCalculator";
import { TradeReasoningCard } from "@/components/TradeReasoningCard";
import { Level2Depth } from "@/components/Level2Depth";
import { NairobiClock } from "@/components/NairobiClock";
import { CompareModal } from "@/components/CompareModal";

const NativeChart = dynamic(() => import("@/components/NativeChart").then(mod => mod.NativeChart), { ssr: false });
import { ArrowLeft, Check, Copy, Layers, ShieldAlert, Star, Target, Zap, ArrowRightLeft, Activity } from "lucide-react";

export default function MarketDetailPage() {
    const params = useParams();
    const rawSymbol = (params?.symbol as string) || "BTC-USD";
    const symbol = decodeURIComponent(rawSymbol).toUpperCase();

    const [candidate, setCandidate] = useState<CandidateRow | null>(null);
    const [payload, setPayload] = useState<CandidateDrawerPayload | null>(null);
    const [tradeHistory, setTradeHistory] = useState<HistoricalSetup[]>([]);
    const [loading, setLoading] = useState(true);
    const [pinned, setPinned] = useState(false);
    const [copied, setCopied] = useState(false);
    const [toast, setToast] = useState<string | null>(null);
    const [showCompare, setShowCompare] = useState(false);

    useEffect(() => {
        setLoading(true);
        fetchCandidates()
            .then((list) => {
                const found = list.find((c) => c.product_id.toLowerCase() === symbol.toLowerCase());
                if (found) {
                    setCandidate(found);
                    setPinned(found.pinned);
                } else {
                    setCandidate({
                        product_id: symbol,
                        last_price: 1.0,
                        day_change_pct: 0,
                        composite_score: 75,
                        trade_direction: "LONG",
                        label: "ENTRY_ZONE",
                        pos_in_range: 0.25,
                        quote_vol_24h: 5000000,
                        ladder: null,
                        tags: ["VWAP_HOLD", "FIB_786"],
                        pinned: false,
                    });
                }
            })
            .catch((err) => console.error("Error fetching candidate:", err));

        fetchMarketLadder(symbol)
            .then((data) => setPayload(data))
            .catch((err) => console.error("Error fetching ladder detail:", err))
            .finally(() => setLoading(false));

        fetchMarketTradeHistory(symbol)
            .then((hist) => setTradeHistory(hist))
            .catch((err) => console.error("Error fetching trade history:", err));
    }, [symbol]);

    const float_to_str = (n: number) => n < 1 ? n.toFixed(4) : n.toLocaleString(undefined, { maximumFractionDigits: 2 });

    const handlePinToggle = async () => {
        if (!candidate) return;
        try {
            if (pinned) {
                await unpinSymbol(candidate.product_id);
                setPinned(false);
                showToast(`Removed ${candidate.product_id} from Watchlist`);
            } else {
                await pinSymbol(candidate.product_id);
                setPinned(true);
                showToast(`Pinned ${candidate.product_id} to Watchlist`);
            }
        } catch (err) {
            console.error("Pin toggle error:", err);
        }
    };

    const handleCopyLadder = () => {
        if (!payload?.copy_text) return;
        navigator.clipboard.writeText(payload.copy_text);
        setCopied(true);
        showToast(`Copied ${symbol} limit-ladder template to clipboard!`);
        setTimeout(() => setCopied(false), 2000);
    };

    const showToast = (msg: string) => {
        setToast(msg);
        setTimeout(() => setToast(null), 3000);
    };

    const formatPrice = (v: number | null | undefined): string => {
        if (v === null || v === undefined) return "-";
        if (v < 0.0001) return `$${v.toFixed(6)}`;
        if (v < 1.0) return `$${v.toFixed(5)}`;
        if (v < 10.0) return `$${v.toFixed(3)}`;
        return `$${v.toFixed(2)}`;
    };

    const lad = payload?.ladder || candidate?.ladder;
    const lastP = candidate?.last_price || 1.0;

    const isShortMath = !!(lad?.stop_price && lad?.tranche_a_price && lad.stop_price > lad.tranche_a_price);
    const effectiveTradeDir = isShortMath ? "SHORT" : (payload?.trade_direction || candidate?.trade_direction || "LONG");

    return (
        <div style={{ minHeight: "100vh", backgroundColor: "var(--bg-dark)", color: "var(--text-main)", padding: "1.25rem 2rem", display: "flex", flexDirection: "column", gap: "1.25rem" }}>
            {/* Toast Notification Banner */}
            {toast && <div className="toast">{toast}</div>}

            {/* Top Navigation & Status Bar */}
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", borderBottom: "none", paddingBottom: "0.85rem" }}>
                <Link
                    href="/"
                    style={{
                        display: "inline-flex",
                        alignItems: "center",
                        gap: "0.5rem",
                        fontSize: "0.75rem",
                        fontWeight: 800,
                        color: "var(--text-muted)",
                        background: "var(--panel-bg)",
                        padding: "0.4rem 0.85rem",
                        borderRadius: 0,
                        border: "none",
                        textDecoration: "none",
                    }}
                >
                    <ArrowLeft size={16} />
                    BACK TO MARKET SCANNER DESK
                </Link>

                <div className="mono" style={{ fontSize: "0.75rem", display: "flex", alignItems: "center", gap: "0.6rem", background: "var(--panel-bg)", padding: "0.4rem 0.85rem", borderRadius: 0, border: "none", color: "var(--text-muted)" }}>
                    <span style={{ width: "7px", height: "7px", borderRadius: "50%", background: "var(--accent-emerald)" }} className="status-pulse" />
                    NAIROBI: <NairobiClock />
                </div>
            </div>

            {/* COMPACT Candidate Header Summary Ribbon */}
            <div style={{ background: "var(--panel-bg)", border: "none", borderRadius: 0, padding: "0.6rem 1rem", display: "flex", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between", gap: "0.75rem" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", flexWrap: "wrap" }}>
                    <button
                        onClick={handlePinToggle}
                        style={{
                            padding: "0.4rem",
                            borderRadius: 0,
                            border: pinned ? "1px solid rgba(245, 158, 11, 0.4)" : "1px solid var(--panel-border)",
                            background: pinned ? "rgba(245, 158, 11, 0.15)" : "rgba(0,0,0,0.4)",
                            color: pinned ? "#F59E0B" : "var(--text-dim)",
                            cursor: "pointer",
                            display: "flex",
                            alignItems: "center"
                        }}
                        title={pinned ? "Unpin Watchlist" : "Pin Watchlist"}
                    >
                        <Star size={16} fill={pinned ? "#F59E0B" : "none"} />
                    </button>

                    <h1 style={{ fontSize: "1.2rem", fontWeight: 800, color: "#FFF", margin: 0, letterSpacing: "-0.02em" }}>{symbol}</h1>

                    {candidate && <span className={`label-badge ${candidate.label}`} style={{ padding: "0.25rem 0.5rem", fontSize: "0.65rem" }}>{candidate.label}</span>}
                    {candidate && (
                        <span className={`label-badge`} style={{ padding: "0.25rem 0.5rem", fontSize: "0.65rem", background: effectiveTradeDir === "SHORT" ? "rgba(244, 63, 94, 0.2)" : "rgba(16, 185, 129, 0.2)", color: effectiveTradeDir === "SHORT" ? "#F43F5E" : "#10B981" }}>
                            {effectiveTradeDir}
                        </span>
                    )}

                    <span className="mono" style={{ color: "var(--text-main)", fontSize: "0.8rem", fontWeight: 700 }}>
                        SPOT: {formatPrice(candidate?.last_price)}
                    </span>

                    {candidate && (
                        <>
                            <span style={{ color: "var(--panel-border)" }}>|</span>
                            <span className="mono" style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                                24h Vol: ${(candidate.quote_vol_24h / 1_000_000).toFixed(2)}M
                            </span>
                            <span style={{ color: "var(--panel-border)" }}>|</span>
                            <span className="mono" style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                                PIR: {candidate.pos_in_range.toFixed(2)}
                            </span>
                        </>
                    )}
                </div>

                {/* Score, 24h Change & Actions in compact format */}
                {candidate && (
                    <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
                        <div style={{ display: "flex", alignItems: "baseline", gap: "0.4rem" }}>
                            <span style={{ fontSize: "0.65rem", color: "var(--text-dim)", fontWeight: 800, textTransform: "uppercase" }}>SCORE:</span>
                            <span className="mono" style={{ fontSize: "1.1rem", fontWeight: 800, color: "var(--accent-emerald)" }}>
                                {candidate.composite_score.toFixed(0)}<span style={{ fontSize: "0.7rem", color: "var(--text-dim)", fontWeight: 400 }}>/100</span>
                            </span>
                        </div>

                        <div style={{ display: "flex", alignItems: "baseline", gap: "0.4rem", paddingLeft: "1rem", borderLeft: "none" }}>
                            <span style={{ fontSize: "0.65rem", color: "var(--text-dim)", fontWeight: 800, textTransform: "uppercase" }}>24H:</span>
                            <span className="mono" style={{ fontSize: "1rem", fontWeight: 800, color: candidate.day_change_pct >= 0 ? "var(--accent-emerald)" : "var(--accent-rose)" }}>
                                {candidate.day_change_pct >= 0 ? `+${candidate.day_change_pct.toFixed(2)}%` : `${candidate.day_change_pct.toFixed(2)}%`}
                            </span>
                        </div>

                        {payload?.score_breakdown?.funding_rate !== undefined && (
                            <div style={{ display: "flex", alignItems: "baseline", gap: "0.4rem", paddingLeft: "1rem", borderLeft: "none" }}>
                                <span style={{ fontSize: "0.65rem", color: "var(--text-dim)", fontWeight: 800, textTransform: "uppercase" }}>FUNDING:</span>
                                <span className="mono" style={{ fontSize: "0.9rem", fontWeight: 800, color: payload.score_breakdown.funding_rate < -0.0001 ? "var(--accent-emerald)" : "var(--text-main)" }}>
                                    {(payload.score_breakdown.funding_rate * 100).toFixed(4)}%
                                </span>
                            </div>
                        )}

                        {payload?.score_breakdown?.oi_change_pct !== undefined && payload.score_breakdown.oi_change_pct !== 0 && (
                            <div style={{ display: "flex", alignItems: "baseline", gap: "0.4rem", paddingLeft: "1rem", borderLeft: "none" }}>
                                <span style={{ fontSize: "0.65rem", color: "var(--text-dim)", fontWeight: 800, textTransform: "uppercase" }}>OI:</span>
                                <span className="mono" style={{ fontSize: "0.9rem", fontWeight: 800, color: payload.score_breakdown.oi_change_pct >= 0 ? "var(--accent-emerald)" : "var(--accent-rose)" }}>
                                    {payload.score_breakdown.oi_change_pct > 0 ? `+${payload.score_breakdown.oi_change_pct.toFixed(2)}%` : `${payload.score_breakdown.oi_change_pct.toFixed(2)}%`}
                                </span>
                            </div>
                        )}

                        {payload?.copy_text && (
                            <button
                                onClick={handleCopyLadder}
                                className="mono"
                                style={{
                                    display: "flex",
                                    alignItems: "center",
                                    gap: "0.4rem",
                                    fontSize: "0.75rem",
                                    fontWeight: 800,
                                    padding: "0.4rem 0.8rem",
                                    borderRadius: 0,
                                    border: copied ? "1px solid #10B981" : "1px solid rgba(6, 182, 212, 0.4)",
                                    background: copied ? "#10B981" : "rgba(6, 182, 212, 0.15)",
                                    color: copied ? "#000" : "var(--accent-cyan)",
                                    cursor: "pointer",
                                    transition: "all 0.15s ease",
                                    marginLeft: "0.5rem"
                                }}
                            >
                                {copied ? <Check size={14} /> : <Copy size={14} />}
                                {copied ? "COPIED!" : "COPY LADDER"}
                            </button>
                        )}

                        {candidate && (
                            <button
                                onClick={() => setShowCompare(true)}
                                className="mono"
                                style={{
                                    display: "flex",
                                    alignItems: "center",
                                    gap: "0.4rem",
                                    fontSize: "0.75rem",
                                    fontWeight: 800,
                                    padding: "0.4rem 0.8rem",
                                    borderRadius: 0,
                                    border: "none",
                                    background: "rgba(168, 85, 247, 0.15)",
                                    color: "#C084FC",
                                    cursor: "pointer",
                                    transition: "all 0.15s ease",
                                    marginLeft: "0.2rem"
                                }}
                            >
                                <ArrowRightLeft size={14} />
                                COMPARE
                            </button>
                        )}
                    </div>
                )}
            </div>

            {/* DOMINANT HERO CHART CANVAS WITH FLOATING ENTRY & TARGET ZONES HUD */}
            <div style={{ display: "flex", flexDirection: "column", gap: "0.6rem" }}>
                {/* Floating Entry & Target Zones HUD Bar */}
                <div style={{ background: "#05070D", border: "none", borderRadius: 0, padding: "0.6rem 1rem", display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "0.75rem" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                        <Layers size={16} color="var(--accent-cyan)" />
                        <span style={{ fontWeight: 800, fontSize: "0.75rem", color: "#FFF", letterSpacing: "0.04em" }}>ACTIVE SETUP LEVEL ZONES:</span>
                    </div>

                    <div style={{ display: "flex", alignItems: "center", gap: "0.6rem", flexWrap: "wrap" }}>
                        {/* Tranche A Zone */}
                        <div className="mono" style={{ background: "rgba(16, 185, 129, 0.12)", border: "none", borderRadius: 0, padding: "0.3rem 0.6rem", display: "flex", alignItems: "center", gap: "0.35rem", fontSize: "0.72rem" }}>
                            <span style={{ width: "6px", height: "6px", borderRadius: "50%", background: "#34D399" }} />
                            <span style={{ color: "var(--text-muted)" }}>TRANCHE A (60%):</span>
                            <span style={{ color: "#34D399", fontWeight: 800 }}>{formatPrice(lad?.tranche_a_price || lastP * 0.99)}</span>
                        </div>

                        {/* Tranche B Zone */}
                        <div className="mono" style={{ background: "rgba(6, 182, 212, 0.12)", border: "none", borderRadius: 0, padding: "0.3rem 0.6rem", display: "flex", alignItems: "center", gap: "0.35rem", fontSize: "0.72rem" }}>
                            <span style={{ width: "6px", height: "6px", borderRadius: 0, background: "#38BDF8" }} />
                            <span style={{ color: "var(--text-muted)" }}>TRANCHE B (40%):</span>
                            <span style={{ color: "#38BDF8", fontWeight: 800 }}>{formatPrice(lad?.tranche_b_price || lastP * 0.97)}</span>
                        </div>

                        {/* Stop Loss Zone */}
                        <div className="mono" style={{ background: "rgba(244, 63, 94, 0.12)", border: "none", borderRadius: 0, padding: "0.3rem 0.6rem", display: "flex", alignItems: "center", gap: "0.35rem", fontSize: "0.72rem" }}>
                            <ShieldAlert size={12} color="#F87171" />
                            <span style={{ color: "var(--text-muted)" }}>STOP LOSS:</span>
                            <span style={{ color: "#F87171", fontWeight: 800 }}>{formatPrice(lad?.stop_price || lastP * 0.95)}</span>
                        </div>

                        {/* Target 1 Zone */}
                        <div className="mono" style={{ background: "rgba(59, 130, 246, 0.12)", border: "none", borderRadius: 0, padding: "0.3rem 0.6rem", display: "flex", alignItems: "center", gap: "0.35rem", fontSize: "0.72rem" }}>
                            <Target size={12} color="#60A5FA" />
                            <span style={{ color: "var(--text-muted)" }}>TARGET 1:</span>
                            <span style={{ color: "#60A5FA", fontWeight: 800 }}>{formatPrice(lad?.target_1_price || lastP * 1.05)}</span>
                        </div>

                        {/* Target 2 Zone */}
                        <div className="mono" style={{ background: "rgba(168, 85, 247, 0.12)", border: "none", borderRadius: 0, padding: "0.3rem 0.6rem", display: "flex", alignItems: "center", gap: "0.35rem", fontSize: "0.72rem" }}>
                            <Zap size={12} color="#C084FC" />
                            <span style={{ color: "var(--text-muted)" }}>TARGET 2:</span>
                            <span style={{ color: "#C084FC", fontWeight: 800 }}>{formatPrice(lad?.target_2_price || lastP * 1.10)}</span>
                        </div>
                    </div>
                </div>

                {/* Dominant Native Chart Container (650px canvas height) */}
                <NativeChart
                    productId={symbol}
                    height="650px"
                    entryLevel={lad?.tranche_a_price}
                    tpLevel={lad?.target_1_price}
                    slLevel={lad?.stop_price}
                    ladder={lad || null}
                    features={payload?.features || null}
                    tradeHistory={tradeHistory}
                    tradeDirection={effectiveTradeDir}
                />
            </div>

            {/* 4-COLUMN STRUCTURED DATA GRID BELOW CHART */}
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1.5fr 1fr", gap: "1.25rem" }}>
                {/* Column 1: Order Sizing & Risk/Reward Calculator Desk */}
                <SetupCalculator
                    symbol={symbol}
                    lastPrice={candidate?.last_price || 1.0}
                    ladder={lad || null}
                />

                {/* Column 2: Limit Ladder Target Matrix */}
                <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                        <Target size={18} color="var(--accent-emerald)" />
                        <h3 style={{ fontSize: "0.85rem", fontWeight: 800, color: "#FFF", letterSpacing: "0.03em" }}>
                            LIMIT LADDER TARGET MATRIX
                        </h3>
                    </div>
                    {lad ? (
                        <LimitLadderOverlay ladder={lad} lastPrice={candidate?.last_price || 1.0} />
                    ) : (
                        <div style={{ padding: "2rem", background: "#0B0F19", borderRadius: 0, border: "none", textAlign: "center", fontSize: "0.75rem", color: "var(--text-dim)" }}>
                            Computing order targets...
                        </div>
                    )}
                </div>

                {/* Column 3: Structured Trade Thesis & Formatted Order Block */}
                <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
                    {payload?.options_flow && payload.options_flow.gamma_walls && (
                        <div style={{ background: "#0B0F19", border: "none", padding: "1rem", display: "flex", flexDirection: "column", gap: "0.75rem" }}>
                            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                                <Activity size={16} color="#A855F7" />
                                <span style={{ fontSize: "0.72rem", fontWeight: 800, color: "#A855F7", textTransform: "uppercase", letterSpacing: "0.04em" }}>Options Gamma Engine</span>
                            </div>
                            <div className="mono" style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>
                                <div style={{ display: "flex", justifyContent: "space-between", borderBottom: "1px dashed rgba(255,255,255,0.05)", paddingBottom: "0.4rem", marginBottom: "0.4rem" }}>
                                    <span>NET DEALER GEX:</span>
                                    <span style={{ color: payload.options_flow.total_net_gex >= 0 ? "#10B981" : "#F87171", fontWeight: 800 }}>
                                        {payload.options_flow.total_net_gex >= 0 ? "+" : ""}{(payload.options_flow.total_net_gex / 1_000_000).toFixed(2)}M
                                    </span>
                                </div>

                                <div style={{ display: "flex", justifyContent: "space-between", borderBottom: "1px dashed rgba(255,255,255,0.05)", paddingBottom: "0.4rem", marginBottom: "0.4rem" }}>
                                    <span>GAMMA FLIP:</span>
                                    <span style={{ color: "#FFF", fontWeight: 800 }}>${payload.options_flow.gamma_flip.toLocaleString()}</span>
                                </div>

                                <div style={{ display: "flex", flexDirection: "column", gap: "0.3rem" }}>
                                    {payload.options_flow.gamma_walls.slice(0, 3).map((w: any, idx: number) => (
                                        <div key={idx} style={{ display: "flex", justifyContent: "space-between" }}>
                                            <span>STRIKE ${float_to_str(w.strike)} {w.type == "RESISTANCE" ? "(CALL WALL)" : "(PUT WALL)"}</span>
                                            <span style={{ color: w.type === "RESISTANCE" ? "#F43F5E" : "#10B981", fontWeight: 800, fontSize: "0.65rem" }}>{w.type}</span>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        </div>
                    )}

                    {candidate && <TradeReasoningCard candidate={candidate} />}

                    {payload?.copy_text && (
                        <div style={{ background: "#0B0F19", border: "none", borderRadius: 0, padding: "1rem", display: "flex", flexDirection: "column", gap: "0.4rem" }}>
                            <span style={{ fontSize: "0.65rem", color: "var(--text-dim)", fontWeight: 800, textTransform: "uppercase" }}>
                                PRD §8 Formatted Order Template
                            </span>
                            <div className="code-block" style={{ margin: 0, fontSize: "0.72rem", overflowX: "auto" }}>
                                {payload.copy_text}
                            </div>
                        </div>
                    )}
                </div>

                {/* Column 4: L2 Orderbook Depth & Liquidity Stream */}
                <Level2Depth symbol={symbol} />
            </div>

            {/* Compare Modal Injection */}
            {showCompare && candidate && (
                <CompareModal
                    baseAsset={candidate}
                    onClose={() => setShowCompare(false)}
                />
            )}
        </div>
    );
}
