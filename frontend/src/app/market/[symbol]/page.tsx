"use client";

import React, { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import dynamic from "next/dynamic";
import {
    CandidateDrawerPayload,
    CandidateRow,
    HistoricalSetup,
    ScoringWeightsConfig,
    fetchCandidates,
    fetchMarketLadder,
    fetchMarketTradeHistory,
    fetchScoringWeights,
    pinSymbol,
    unpinSymbol,
} from "@/lib/api";
import { LimitLadderOverlay } from "@/components/LimitLadderOverlay";
import { SetupCalculator } from "@/components/SetupCalculator";
import { TradeReasoningCard } from "@/components/TradeReasoningCard";
import { ScoreBreakdownPanel } from "@/components/ScoreBreakdown";
import { CoverageBadge, coverageOpacity } from "@/components/CoverageBadge";
import { EmptyState, Panel, SectionTitle, Skeleton } from "@/components/ui";
import { Level2Depth } from "@/components/Level2Depth";
import { NairobiClock } from "@/components/NairobiClock";
import { CompareModal } from "@/components/CompareModal";
import { TopScannedAssetsTable } from "@/components/TopScannedAssetsTable";
import { SetupSummaryRail } from "@/components/SetupSummaryRail";
import { ScoreExplanationModal } from "@/components/ScoreExplanationModal";
import { DeepAnalyticalToolsDrawer } from "@/components/DeepAnalyticalToolsDrawer";

const NativeChart = dynamic(
    () => import("@/components/NativeChart").then((mod) => mod.NativeChart || mod.default),
    {
        ssr: false,
        loading: () => <Skeleton height="740px" />,
    }
);
import { Activity, AlertTriangle, ArrowLeft, ArrowRightLeft, Check, ChevronDown, ChevronUp, Copy, Layers, Star, Target } from "lucide-react";

/** The scheduler runs every 300s, so anything past this is worth flagging. */
const STALE_MINUTES = 15;

export default function MarketDetailPage() {
    const params = useParams();
    const rawSymbol = (params?.symbol as string) || "BTC-USD";
    const symbol = decodeURIComponent(rawSymbol).toUpperCase();

    const [candidate, setCandidate] = useState<CandidateRow | null>(null);
    const [candidates, setCandidates] = useState<CandidateRow[]>([]);
    const [payload, setPayload] = useState<CandidateDrawerPayload | null>(null);
    const [tradeHistory, setTradeHistory] = useState<HistoricalSetup[]>([]);
    const [scoring, setScoring] = useState<ScoringWeightsConfig | null>(null);
    const [loading, setLoading] = useState(true);
    const [notInScan, setNotInScan] = useState(false);
    const [pinned, setPinned] = useState(false);
    const [copied, setCopied] = useState(false);
    const [toast, setToast] = useState<string | null>(null);
    const [showCompare, setShowCompare] = useState(false);
    const [showScoreExplanation, setShowScoreExplanation] = useState(false);
    const [showSecondaryTools, setShowSecondaryTools] = useState(false);
    const [now, setNow] = useState<number | null>(null);

    useEffect(() => {
        let cancelled = false;
        let isInitial = true;

        // Load scoring weights ONCE on mount — they don't change per page visit.
        fetchScoringWeights()
            .then((cfg) => { if (!cancelled && cfg) setScoring(cfg); })
            .catch(() => { });

        // 1. Single-Asset Data: ladder + trade history (fast DB reads, server-cached 30s).
        const loadSingleAssetData = async () => {
            if (isInitial) {
                setLoading(true);
                setNotInScan(false);
            }

            try {
                const [ladderData, tradeHist] = await Promise.all([
                    fetchMarketLadder(symbol).catch((err) => { console.error("Error fetching ladder detail:", err); return null; }),
                    fetchMarketTradeHistory(symbol).catch((err) => { console.error("Error fetching trade history:", err); return null; }),
                ]);

                if (cancelled) return;

                if (ladderData) {
                    setPayload(ladderData);
                    if (ladderData.features) {
                        const builtCandidate: CandidateRow = {
                            product_id: symbol,
                            last_price: ladderData.features.last_price || 0,
                            day_change_pct: 0,
                            quote_vol_24h: 0,
                            composite_score: ladderData.composite_score || 0,
                            label: ladderData.label || "NEUTRAL",
                            trade_direction: ladderData.trade_direction || "LONG",
                            coverage: ladderData.coverage || null,
                            coverage_band: ladderData.coverage_band || null,
                            edge: ladderData.edge || null,
                            pos_in_range: 0.5,
                            tags: [],
                            pinned: false,
                            ladder: ladderData.ladder || null,
                        };
                        setCandidate((prev) => prev || builtCandidate);
                    }
                    setNotInScan(false);
                } else if (!ladderData && isInitial) {
                    setNotInScan(true);
                }

                if (tradeHist) setTradeHistory(tradeHist);
            } finally {
                if (isInitial && !cancelled) {
                    setLoading(false);
                    isInitial = false;
                }
            }
        };

        // 2. Global candidates list — background, infrequent (60s poll).
        const loadGlobalCandidates = async () => {
            try {
                const list = await fetchCandidates().catch((err) => {
                    console.error("Error fetching global candidates list:", err);
                    return null;
                });
                if (cancelled || !list) return;

                setCandidates(list);
                const found = list.find((c) => c.product_id.toLowerCase() === symbol.toLowerCase());
                if (found) {
                    setCandidate(found);
                    setPinned(found.pinned);
                    setNotInScan(false);
                }
            } catch (err) {
                console.error("Background candidates fetch error:", err);
            }
        };

        loadSingleAssetData();
        loadGlobalCandidates();

        // Poll asset detail every 20s (server cache is 30s, so this is light).
        const singleAssetInterval = setInterval(loadSingleAssetData, 20000);
        // Poll full candidates list every 60s — rarely changes between scans.
        const globalListInterval = setInterval(loadGlobalCandidates, 60000);

        return () => {
            cancelled = true;
            clearInterval(singleAssetInterval);
            clearInterval(globalListInterval);
        };
    }, [symbol]);

    useEffect(() => {
        setNow(Date.now());
        const id = setInterval(() => setNow(Date.now()), 5_000);
        return () => clearInterval(id);
    }, []);

    const rank = useMemo(() => {
        if (!candidate || candidates.length === 0) return null;
        const sorted = [...candidates].sort((a, b) => b.composite_score - a.composite_score);
        const idx = sorted.findIndex((c) => c.product_id === candidate.product_id);
        return idx >= 0 ? { position: idx + 1, total: sorted.length } : null;
    }, [candidate, candidates]);

    const ageMinutes = useMemo(() => {
        if (now === null || !payload?.updated_at) return null;
        const t = Date.parse(payload.updated_at);
        return Number.isNaN(t) ? null : Math.max(0, Math.floor((now - t) / 60_000));
    }, [now, payload?.updated_at]);

    const isStale = ageMinutes !== null && ageMinutes >= STALE_MINUTES;

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
        if (v === null || v === undefined) return "—";
        if (v < 0.0001) return `$${v.toFixed(6)}`;
        if (v < 1.0) return `$${v.toFixed(4)}`;
        if (v < 10.0) return `$${v.toFixed(3)}`;
        return `$${v.toFixed(2)}`;
    };

    const lad = payload?.ladder || candidate?.ladder || null;
    const lastP = candidate?.last_price ?? payload?.features?.last_price ?? null;

    const isShortMath = !!(lad?.stop_price && lad?.tranche_a_price && lad.stop_price > lad.tranche_a_price);
    const effectiveTradeDir = isShortMath ? "SHORT" : (payload?.trade_direction || candidate?.trade_direction || "LONG");

    const coverage = payload?.coverage ?? candidate?.coverage ?? null;
    const coverageBand = payload?.coverage_band ?? candidate?.coverage_band ?? null;
    const edge = payload?.edge ?? candidate?.edge ?? null;

    const coldLoad = loading && !candidate && !payload;

    const symbolBase = symbol.split("-")[0];
    const assetFullName = symbolBase === "ICP" ? "Internet Computer" : (symbolBase === "BTC" ? "Bitcoin" : (symbolBase === "ETH" ? "Ethereum" : `${symbolBase} Token`));

    return (
        <div style={{ minHeight: "100vh", backgroundColor: "var(--bg-dark)", color: "var(--text-main)", padding: "1rem 1.5rem", display: "flex", flexDirection: "column", gap: "1rem" }}>
            {toast && <div className="toast">{toast}</div>}

            {/* 1. Top Navigation & System Status Bar */}
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "1rem", flexWrap: "wrap" }}>
                <Link
                    href="/"
                    style={{
                        display: "inline-flex",
                        alignItems: "center",
                        gap: "0.4rem",
                        fontSize: "0.72rem",
                        fontWeight: 800,
                        color: "var(--text-muted)",
                        background: "rgba(255,255,255,0.03)",
                        padding: "0.35rem 0.75rem",
                        borderRadius: "3px",
                        border: "1px solid rgba(255,255,255,0.06)",
                        textDecoration: "none",
                        letterSpacing: "0.04em",
                    }}
                >
                    <ArrowLeft size={14} />
                    SCANNER
                </Link>

                <div style={{ display: "flex", alignItems: "center", gap: "1rem", fontSize: "0.72rem", fontFamily: "var(--font-jetbrains)" }}>
                    <div style={{ color: "var(--warn)", display: "flex", alignItems: "center", gap: "0.35rem" }}>
                        <AlertTriangle size={13} color="var(--warn)" />
                        Levels computed {ageMinutes != null ? `${ageMinutes}m` : "recently"} ago · Scanner active
                    </div>

                    <div style={{ color: "var(--pos)", display: "flex", alignItems: "center", gap: "0.35rem" }}>
                        <span style={{ width: "6px", height: "6px", borderRadius: "50%", background: "var(--pos)" }} className="status-pulse" />
                        LIVE
                    </div>

                    <div style={{ color: "var(--text-dim)" }}>
                        <NairobiClock />
                    </div>
                </div>
            </div>

            {/* Staleness Warning Banners */}
            {isStale && !coldLoad && (
                <EmptyState icon={<AlertTriangle size={14} color="var(--warn)" style={{ flexShrink: 0, marginTop: "1px" }} />}>
                    These levels were computed <strong>{ageMinutes} minutes ago</strong> and the scanner re-runs every 5.
                    Treat the ladder as indicative until the next scan completes.
                </EmptyState>
            )}

            {notInScan && !coldLoad && (
                <EmptyState icon={<AlertTriangle size={14} color="var(--warn)" style={{ flexShrink: 0, marginTop: "1px" }} />}>
                    <strong>{symbol}</strong> was not in the latest scan, so there is no score, label or ladder for it.
                </EmptyState>
            )}

            {coldLoad ? (
                <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-4)" }}>
                    <Skeleton height="3.5rem" />
                    <Skeleton height="40rem" />
                </div>
            ) : (
                <>
                    {/* 2. HORIZONTAL TERMINAL MARKET HEADER STRIP */}
                    <div style={{
                        background: "var(--panel-bg)",
                        border: "1px solid rgba(255, 255, 255, 0.08)",
                        borderRadius: "4px",
                        padding: "0.75rem 1.25rem",
                        display: "flex",
                        flexWrap: "wrap",
                        alignItems: "center",
                        justifyContent: "space-between",
                        gap: "1.25rem",
                    }}>
                        {/* Asset Identity */}
                        <div style={{ display: "flex", alignItems: "center", gap: "0.85rem" }}>
                            <button
                                onClick={handlePinToggle}
                                disabled={!candidate}
                                style={{
                                    background: "none", border: "none", padding: 0, cursor: candidate ? "pointer" : "default"
                                }}
                            >
                                <Star size={18} fill={pinned ? "var(--warn)" : "none"} color={pinned ? "var(--warn)" : "var(--text-dim)"} />
                            </button>

                            <div style={{
                                width: "36px", height: "36px", borderRadius: "50%",
                                background: "rgba(6, 182, 212, 0.15)", border: "1px solid rgba(6, 182, 212, 0.4)",
                                display: "flex", alignItems: "center", justifyContent: "center",
                                fontSize: "1rem", fontWeight: 900, color: "var(--info)"
                            }}>
                                {symbolBase.slice(0, 1)}
                            </div>

                            <div>
                                <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                                    <h1 style={{ fontSize: "1.25rem", fontWeight: 900, color: "var(--text-strong)", margin: 0, letterSpacing: "-0.02em" }}>{symbol}</h1>
                                </div>
                                <div style={{ fontSize: "0.72rem", color: "var(--text-4)", fontWeight: 500 }}>
                                    {assetFullName}
                                </div>
                            </div>
                        </div>

                        {/* Price & 24h Change */}
                        <div>
                            <div style={{ fontSize: "1.3rem", fontWeight: 900, color: "var(--text-strong)", fontFamily: "var(--font-jetbrains)" }}>
                                {formatPrice(lastP)}
                            </div>
                            <div style={{ fontSize: "0.75rem", fontWeight: 800, color: (candidate?.day_change_pct ?? 0) >= 0 ? "var(--pos)" : "var(--neg-bright)", fontFamily: "var(--font-jetbrains)" }}>
                                {candidate?.day_change_pct != null ? `${candidate.day_change_pct >= 0 ? "+" : ""}${candidate.day_change_pct.toFixed(2)}%` : "—"} (24h)
                            </div>
                        </div>

                        {/* Direction & Status Badges */}
                        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                            <div style={{
                                padding: "0.35rem 0.8rem",
                                borderRadius: "3px",
                                fontSize: "0.8rem",
                                fontWeight: 900,
                                background: effectiveTradeDir === "SHORT" ? "rgba(244, 63, 94, 0.2)" : "rgba(16, 185, 129, 0.2)",
                                color: effectiveTradeDir === "SHORT" ? "var(--neg-bright)" : "var(--pos)",
                                border: effectiveTradeDir === "SHORT" ? "1px solid rgba(244, 63, 94, 0.4)" : "1px solid rgba(16, 185, 129, 0.4)",
                                letterSpacing: "0.05em"
                            }}>
                                {effectiveTradeDir}
                            </div>

                            {candidate?.label && (
                                <div style={{
                                    padding: "0.35rem 0.75rem",
                                    borderRadius: "3px",
                                    fontSize: "0.75rem",
                                    fontWeight: 800,
                                    background: "rgba(255, 255, 255, 0.05)",
                                    color: "var(--text-main)",
                                    border: "1px solid rgba(255, 255, 255, 0.1)"
                                }}>
                                    {candidate.label}
                                </div>
                            )}
                        </div>

                        {/* Market Metrics Strip */}
                        <div style={{ display: "flex", alignItems: "center", gap: "1.5rem", fontFamily: "var(--font-jetbrains)", fontSize: "0.75rem" }}>
                            <div>
                                <div style={{ fontSize: "0.62rem", color: "var(--text-4)", fontWeight: 800, textTransform: "uppercase" }}>24H VOL</div>
                                <div style={{ color: "var(--text-main)", fontWeight: 800 }}>
                                    {candidate?.quote_vol_24h != null ? `$${(candidate.quote_vol_24h / 1e6).toFixed(2)}M` : "—"}
                                </div>
                            </div>

                            <div>
                                <div style={{ fontSize: "0.62rem", color: "var(--text-4)", fontWeight: 800, textTransform: "uppercase" }}>FUNDING</div>
                                {(() => {
                                    const fr = payload?.score_breakdown?.funding_rate ?? null;
                                    return (
                                        <div style={{ color: fr !== null ? (fr >= 0 ? "var(--pos)" : "var(--neg-bright)") : "var(--text-dim)", fontWeight: 800 }}>
                                            {fr !== null ? `${fr >= 0 ? "+" : ""}${(fr * 100).toFixed(4)}%` : "—"}
                                        </div>
                                    );
                                })()}
                            </div>

                            <div>
                                <div style={{ fontSize: "0.62rem", color: "var(--text-4)", fontWeight: 800, textTransform: "uppercase" }}>OPEN INTEREST</div>
                                {(() => {
                                    const oi = payload?.score_breakdown?.oi_change_pct ?? null;
                                    return (
                                        <div style={{ color: oi !== null ? (oi >= 0 ? "var(--pos)" : "var(--neg-bright)") : "var(--text-dim)", fontWeight: 800 }}>
                                            {oi !== null ? `${oi >= 0 ? "+" : ""}${oi.toFixed(2)}%` : "—"}
                                        </div>
                                    );
                                })()}
                            </div>
                        </div>

                        {/* SCANNER SCORE Container */}
                        <div
                            onClick={() => setShowScoreExplanation(true)}
                            style={{
                                background: "rgba(6, 182, 212, 0.08)",
                                border: "1px solid rgba(6, 182, 212, 0.4)",
                                borderRadius: "4px",
                                padding: "0.4rem 1rem",
                                display: "flex",
                                flexDirection: "column",
                                alignItems: "center",
                                justifyContent: "center",
                                boxShadow: "0 0 15px rgba(6, 182, 212, 0.15)",
                                cursor: "pointer",
                                transition: "transform 0.1s ease",
                            }}
                            title="Click to view score composition"
                        >
                            <div style={{ fontSize: "0.6rem", fontWeight: 800, color: "var(--info)", letterSpacing: "0.08em" }}>
                                SCANNER SCORE ⓘ
                            </div>
                            <div style={{ fontSize: "1.3rem", fontWeight: 900, color: "#ffffff", lineHeight: 1, fontFamily: "var(--font-jetbrains)" }}>
                                {candidate?.composite_score != null ? candidate.composite_score.toFixed(0) : "—"} <span style={{ fontSize: "0.7rem", color: "var(--text-4)", fontWeight: 400 }}>/100</span>
                            </div>
                        </div>

                        {/* RANK Container */}
                        <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", fontFamily: "var(--font-jetbrains)" }}>
                            <div style={{ fontSize: "0.62rem", color: "var(--text-4)", fontWeight: 800 }}>RANK</div>
                            <div style={{ fontSize: "1.rem", fontWeight: 900, color: "var(--text-strong)" }}>
                                {rank ? `#${rank.position}` : "—"} <span style={{ fontSize: "0.72rem", color: "var(--text-4)", fontWeight: 400 }}>{rank ? `/${rank.total}` : ""}</span>
                            </div>
                        </div>
                    </div>

                    {/* 3. CENTRAL WORKSPACE GRID (CHART WORKSPACE + PERSISTENT SETUP SUMMARY RAIL) */}
                    <div style={{ display: "flex", gap: "1rem", flexWrap: "wrap", alignItems: "flex-start" }}>
                        {/* LEFT COLUMN: PRIMARY CHART WORKSPACE */}
                        <div style={{ flex: 1, minWidth: "600px", display: "flex", flexDirection: "column", gap: "0.6rem" }}>
                            <NativeChart
                                productId={symbol}
                                height="740px"
                                entryLevel={lad?.tranche_a_price}
                                tpLevel={lad?.target_1_price}
                                slLevel={lad?.stop_price}
                                ladder={lad || null}
                                features={payload?.features || null}
                                optionsFlow={payload?.options_flow || null}
                                tradeHistory={tradeHistory}
                                tradeDirection={effectiveTradeDir}
                            />
                        </div>

                        {/* RIGHT COLUMN: PERSISTENT SETUP SUMMARY RAIL */}
                        <SetupSummaryRail
                            candidate={candidate}
                            payload={payload}
                            symbol={symbol}
                            effectiveTradeDir={effectiveTradeDir}
                            rank={rank}
                            onCompareClick={() => setShowCompare(true)}
                            onScoreClick={() => setShowScoreExplanation(true)}
                        />
                    </div>

                    {/* 4. BOTTOM SECTION: TOP SCANNED ASSETS TABLE */}
                    <TopScannedAssetsTable
                        candidates={candidates}
                        currentSymbol={symbol}
                    />

                    {/* 5. DEEP ANALYTICAL TOOLS TABBED DRAWER */}
                    <DeepAnalyticalToolsDrawer
                        symbol={symbol}
                        lastPrice={lastP ?? 0}
                        ladder={lad}
                        payload={payload}
                        candidate={candidate}
                        scoring={scoring}
                        effectiveTradeDir={effectiveTradeDir}
                        rank={rank}
                    />
                </>
            )}

            {showCompare && candidate && (
                <CompareModal
                    baseAsset={candidate}
                    onClose={() => setShowCompare(false)}
                />
            )}

            {showScoreExplanation && (
                <ScoreExplanationModal
                    candidate={candidate}
                    payload={payload}
                    onClose={() => setShowScoreExplanation(false)}
                />
            )}
        </div>
    );
}
