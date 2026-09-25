"use client";

import React, { useEffect, useState } from "react";
import {
    Activity,
    AlertTriangle,
    CheckCircle2,
    ChevronDown,
    ChevronUp,
    Database,
    Download,
    Flame,
    Layers,
    Lock,
    Play,
    RefreshCw,
    ShieldAlert,
    ShieldCheck,
    Zap,
} from "lucide-react";
import {
    expandHistory,
    fetchPluggableStrategies,
    fetchResearchSummary,
    fetchShadowPipelines,
    promoteShadowPipeline,
    type ResearchSummaryResponse,
    runWalkForwardBacktest,
    type ShadowPipeline,
    stageCandidateStrategy,
    type StrategyPlugin,
    type WalkForwardCandidateResult,
} from "@/lib/api";

export const ResearchDashboard: React.FC = () => {
    const [summary, setSummary] = useState<ResearchSummaryResponse | null>(null);
    const [pipelines, setPipelines] = useState<ShadowPipeline[]>([]);
    const [plugins, setPlugins] = useState<StrategyPlugin[]>([]);
    const [selectedStrategyId, setSelectedStrategyId] = useState<string>("all");
    const [loadingSummary, setLoadingSummary] = useState(true);
    const [expanding, setExpanding] = useState(false);
    const [backtesting, setBacktesting] = useState(false);
    const [candidates, setCandidates] = useState<WalkForwardCandidateResult[]>([]);
    const [expandedCandidate, setExpandedCandidate] = useState<string | null>(null);

    // Modal state for explicit manual promotion
    const [promotingPipeline, setPromotingPipeline] = useState<ShadowPipeline | null>(null);
    const [promoting, setPromoting] = useState(false);
    const [actionMsg, setActionMsg] = useState<{ type: "pos" | "neg"; text: string } | null>(null);

    const loadData = async () => {
        setLoadingSummary(true);
        try {
            const [sumData, shadowData, stratData] = await Promise.all([
                fetchResearchSummary(),
                fetchShadowPipelines(),
                fetchPluggableStrategies().catch(() => ({ strategies: [] })),
            ]);
            setSummary(sumData);
            setPipelines(shadowData.pipelines || []);
            setPlugins(stratData.strategies || []);
        } catch (err: any) {
            console.error("Failed to load research summary:", err);
        } finally {
            setLoadingSummary(false);
        }
    };

    useEffect(() => {
        loadData();
    }, []);

    const handleExpandData = async () => {
        setExpanding(true);
        setActionMsg(null);
        try {
            const res = await expandHistory(["BTC-USD", "ETH-USD", "SOL-USD", "AVAX-USD", "LINK-USD"], 5.0);
            setActionMsg({
                type: "pos",
                text: `Successfully expanded data: ${res.total_candles_fetched.toLocaleString()} candles fetched.`,
            });
            await loadData();
        } catch (err: any) {
            setActionMsg({ type: "neg", text: err.message || "Historical data expansion failed" });
        } finally {
            setExpanding(false);
        }
    };

    const handleRunBacktest = async () => {
        setBacktesting(true);
        setActionMsg(null);
        try {
            const stratId = selectedStrategyId === "all" ? undefined : selectedStrategyId;
            const res = await runWalkForwardBacktest(["BTC-USD", "ETH-USD", "SOL-USD"], stratId);
            setCandidates(res.candidate_rankings || []);
            if (res.candidate_rankings?.length > 0) {
                setExpandedCandidate(res.candidate_rankings[0].candidate_name);
            }
            setActionMsg({
                type: "pos",
                text: `Walk-Forward backtest completed across ${res.candidate_rankings?.length} candidate strategies.`,
            });
        } catch (err: any) {
            setActionMsg({ type: "neg", text: err.message || "Walk-Forward backtest failed" });
        } finally {
            setBacktesting(false);
        }
    };

    const handleStageCandidate = async (cand: WalkForwardCandidateResult) => {
        setActionMsg(null);
        try {
            await stageCandidateStrategy(cand.candidate_name, 60.0);
            setActionMsg({
                type: "pos",
                text: `Staged candidate '${cand.candidate_name}' into shadow mode pipeline.`,
            });
            await loadData();
        } catch (err: any) {
            setActionMsg({ type: "neg", text: err.message || "Staging failed" });
        }
    };

    const handleConfirmPromotion = async () => {
        if (!promotingPipeline) return;
        setPromoting(true);
        setActionMsg(null);
        try {
            const res = await promoteShadowPipeline(promotingPipeline.pipeline_version);
            setActionMsg({
                type: "pos",
                text: res.message || `Promoted ${promotingPipeline.pipeline_version} to live status.`,
            });
            setPromotingPipeline(null);
            await loadData();
        } catch (err: any) {
            setActionMsg({ type: "neg", text: err.message || "Manual promotion failed" });
        } finally {
            setPromoting(false);
        }
    };

    return (
        <div style={{ padding: "1.5rem", maxWidth: "1400px", margin: "0 auto", color: "var(--text-strong)" }}>
            {/* Header Title */}
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.5rem" }}>
                <div>
                    <div style={{ display: "flex", alignItems: "center", gap: "0.6rem" }}>
                        <Zap size={22} color="var(--accent-purple)" />
                        <h1 style={{ fontSize: "1.4rem", fontWeight: 800, margin: 0, letterSpacing: "-0.02em" }}>
                            TAPERADAR RESEARCH PIPELINE
                        </h1>
                        <span className="mono" style={{ background: "rgba(168,85,247,0.15)", color: "var(--accent-purple)", fontSize: "0.7rem", padding: "0.2rem 0.5rem", fontWeight: 700 }}>
                            WALK-FORWARD & SHADOW STAGING
                        </span>
                    </div>
                    <p style={{ margin: "0.3rem 0 0 0", color: "var(--text-muted)", fontSize: "0.82rem" }}>
                        Non-autonomous research infrastructure. Replays live scoring logic over 5-year OHLCV datasets with zero look-ahead bias.
                    </p>
                </div>

                <div style={{ display: "flex", gap: "0.6rem", alignItems: "center" }}>
                    {/* Strategy Selector Dropdown */}
                    <div style={{ display: "flex", alignItems: "center", gap: "0.4rem", background: "rgba(255,255,255,0.03)", padding: "0.3rem 0.6rem", border: "1px solid rgba(255,255,255,0.08)", borderRadius: "4px" }}>
                        <Layers size={14} color="var(--accent-purple)" />
                        <select
                            value={selectedStrategyId}
                            onChange={(e) => setSelectedStrategyId(e.target.value)}
                            className="mono"
                            style={{
                                background: "transparent",
                                color: "var(--text-strong)",
                                border: "none",
                                fontSize: "0.78rem",
                                fontWeight: 700,
                                outline: "none",
                                cursor: "pointer",
                            }}
                        >
                            <option value="all" style={{ background: "#0e1117" }}>⚡ All Strategies & Plugins</option>
                            {plugins.map((p) => (
                                <option key={p.strategy_id} value={p.strategy_id} style={{ background: "#0e1117" }}>
                                    🎯 {p.name} (v{p.version})
                                </option>
                            ))}
                        </select>
                    </div>

                    <button
                        className="mono"
                        onClick={handleExpandData}
                        disabled={expanding}
                        style={{
                            background: "rgba(6,182,212,0.1)",
                            border: "1px solid rgba(6,182,212,0.3)",
                            color: "var(--info)",
                            padding: "0.5rem 1rem",
                            fontWeight: 700,
                            fontSize: "0.78rem",
                            cursor: "pointer",
                            display: "flex",
                            alignItems: "center",
                            gap: "0.4rem",
                        }}
                    >
                        {expanding ? <RefreshCw size={14} className="spin" /> : <Database size={14} />}
                        EXPAND DATA (5Y)
                    </button>

                    <button
                        className="mono"
                        onClick={handleRunBacktest}
                        disabled={backtesting}
                        style={{
                            background: "var(--accent-purple)",
                            border: "none",
                            color: "#fff",
                            padding: "0.5rem 1.2rem",
                            fontWeight: 800,
                            fontSize: "0.78rem",
                            cursor: "pointer",
                            display: "flex",
                            alignItems: "center",
                            gap: "0.4rem",
                        }}
                    >
                        {backtesting ? <RefreshCw size={14} className="spin" /> : <Play size={14} fill="currentColor" />}
                        RUN WALK-FORWARD BACKTEST
                    </button>
                </div>
            </div>

            {/* Notification Banner */}
            {actionMsg && (
                <div
                    style={{
                        padding: "0.75rem 1rem",
                        marginBottom: "1.2rem",
                        fontSize: "0.82rem",
                        fontWeight: 700,
                        background: actionMsg.type === "pos" ? "rgba(16,185,129,0.15)" : "rgba(239,68,68,0.15)",
                        borderLeft: `4px solid ${actionMsg.type === "pos" ? "var(--pos)" : "var(--neg)"}`,
                        color: actionMsg.type === "pos" ? "var(--pos)" : "var(--neg)",
                        display: "flex",
                        alignItems: "center",
                        gap: "0.5rem",
                    }}
                >
                    {actionMsg.type === "pos" ? <CheckCircle2 size={16} /> : <AlertTriangle size={16} />}
                    {actionMsg.text}
                </div>
            )}

            {/* Survivorship Bias Banner */}
            <div
                style={{
                    background: "rgba(245,158,11,0.08)",
                    border: "1px solid rgba(245,158,11,0.25)",
                    padding: "0.85rem 1.2rem",
                    marginBottom: "1.5rem",
                    display: "flex",
                    alignItems: "center",
                    gap: "0.8rem",
                }}
            >
                <ShieldAlert size={20} color="var(--accent-amber)" style={{ flexShrink: 0 }} />
                <div style={{ fontSize: "0.8rem", color: "var(--text-strong)" }}>
                    <span style={{ fontWeight: 800, color: "var(--accent-amber)", marginRight: "0.4rem" }}>
                        METHODOLOGY NOTE:
                    </span>
                    <span className="mono" style={{ background: "rgba(245,158,11,0.15)", padding: "0.15rem 0.4rem", fontWeight: 700 }}>
                        {summary?.survivorship_bias_note || "universe = currently-listed symbols, survivorship bias not corrected"}
                    </span>
                    <span style={{ color: "var(--text-muted)", marginLeft: "0.5rem" }}>
                        All historical backtest setups use ATR-based stop fallbacks (<span className="mono" style={{ color: "var(--accent-purple)" }}>l2_approximated: true</span>).
                    </span>
                </div>
            </div>

            {/* Grid layout: Dataset stats + Staged Shadow Pipelines */}
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1.3fr", gap: "1.2rem", marginBottom: "1.5rem" }}>
                {/* Dataset Overview Card */}
                <div style={{ background: "var(--bg-card)", border: "1px solid rgba(255,255,255,0.08)", padding: "1.2rem" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "1rem" }}>
                        <Database size={16} color="var(--info)" />
                        <h2 style={{ fontSize: "0.95rem", fontWeight: 800, margin: 0, letterSpacing: "-0.01em" }}>
                            HISTORICAL CANDLE STORE
                        </h2>
                    </div>

                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.8rem", marginBottom: "1rem" }}>
                        <div style={{ background: "rgba(14, 20, 36, 0.8)", padding: "0.75rem" }}>
                            <div style={{ fontSize: "0.7rem", color: "var(--text-dim)", fontWeight: 700 }}>SYMBOLS STORED</div>
                            <div className="mono" style={{ fontSize: "1.3rem", fontWeight: 800, color: "var(--info)" }}>
                                {summary?.historical_symbols_count || 0}
                            </div>
                        </div>

                        <div style={{ background: "rgba(14, 20, 36, 0.8)", padding: "0.75rem" }}>
                            <div style={{ fontSize: "0.7rem", color: "var(--text-dim)", fontWeight: 700 }}>TOTAL CANDLES</div>
                            <div className="mono" style={{ fontSize: "1.3rem", fontWeight: 800, color: "var(--accent-purple)" }}>
                                {(summary?.total_candles_stored || 0).toLocaleString()}
                            </div>
                        </div>
                    </div>

                    {/* Symbol listing bounds list */}
                    <div style={{ fontSize: "0.75rem" }}>
                        <div style={{ fontWeight: 700, color: "var(--text-muted)", marginBottom: "0.4rem" }}>
                            SYMBOL LISTING DATE BOUNDS:
                        </div>
                        <div style={{ maxHeight: "140px", overflowY: "auto", display: "flex", flexDirection: "column", gap: "0.35rem" }}>
                            {summary?.symbol_listing_bounds && Object.keys(summary.symbol_listing_bounds).length > 0 ? (
                                Object.entries(summary.symbol_listing_bounds).map(([sym, b]) => (
                                    <div key={sym} className="mono" style={{ display: "flex", justifyContent: "space-between", background: "rgba(255,255,255,0.02)", padding: "0.3rem 0.5rem" }}>
                                        <span style={{ fontWeight: 700, color: "var(--text-strong)" }}>{sym}</span>
                                        <span style={{ color: "var(--text-muted)" }}>
                                            {new Date(b.first_candle_ts * 1000).toLocaleDateString()} — {new Date(b.last_candle_ts * 1000).toLocaleDateString()} ({b.total_candles.toLocaleString()} bars)
                                        </span>
                                    </div>
                                ))
                            ) : (
                                <div style={{ color: "var(--text-dim)", fontStyle: "italic" }}>
                                    No historical bounds logged yet. Click "EXPAND DATA (5Y)" to populate.
                                </div>
                            )}
                        </div>
                    </div>
                </div>

                {/* Staged Shadow Mode Pipelines */}
                <div style={{ background: "var(--bg-card)", border: "1px solid rgba(255,255,255,0.08)", padding: "1.2rem" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
                        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                            <Layers size={16} color="var(--accent-purple)" />
                            <h2 style={{ fontSize: "0.95rem", fontWeight: 800, margin: 0, letterSpacing: "-0.01em" }}>
                                STAGED SHADOW PIPELINES
                            </h2>
                        </div>
                        <div className="mono" style={{ fontSize: "0.72rem", color: "var(--text-dim)" }}>
                            THRESHOLD: <span style={{ color: "var(--accent-amber)", fontWeight: 700 }}>N ≥ 30</span>
                        </div>
                    </div>

                    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem", maxHeight: "250px", overflowY: "auto" }}>
                        {pipelines.length > 0 ? (
                            pipelines.map((p) => (
                                <div
                                    key={p.pipeline_version}
                                    style={{
                                        background: "rgba(14, 20, 36, 0.8)",
                                        border: p.eligible_for_promotion ? "1px solid var(--pos)" : "1px solid rgba(255,255,255,0.06)",
                                        padding: "0.85rem",
                                    }}
                                >
                                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.4rem" }}>
                                        <div>
                                            <span className="mono" style={{ fontWeight: 800, color: "var(--accent-purple)", marginRight: "0.5rem" }}>
                                                {p.pipeline_version}
                                            </span>
                                            <span style={{ fontWeight: 700, fontSize: "0.85rem" }}>{p.candidate_name}</span>
                                        </div>

                                        <span
                                            className="mono"
                                            style={{
                                                fontSize: "0.68rem",
                                                fontWeight: 800,
                                                padding: "0.15rem 0.4rem",
                                                background:
                                                    p.status === "PROMOTED"
                                                        ? "rgba(16,185,129,0.2)"
                                                        : p.eligible_for_promotion
                                                            ? "rgba(245,158,11,0.2)"
                                                            : "rgba(255,255,255,0.08)",
                                                color:
                                                    p.status === "PROMOTED"
                                                        ? "var(--pos)"
                                                        : p.eligible_for_promotion
                                                            ? "var(--accent-amber)"
                                                            : "var(--text-muted)",
                                            }}
                                        >
                                            {p.status}
                                        </span>
                                    </div>

                                    {/* Progress bar */}
                                    <div style={{ marginBottom: "0.6rem" }}>
                                        <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.72rem", color: "var(--text-dim)", marginBottom: "0.2rem" }}>
                                            <span>SHADOW SAMPLE SIZE</span>
                                            <span className="mono" style={{ color: p.sample_count >= p.target_sample_size ? "var(--pos)" : "var(--text-strong)", fontWeight: 700 }}>
                                                {p.sample_count} / {p.target_sample_size} CLOSED TRADES
                                            </span>
                                        </div>
                                        <div style={{ height: "6px", background: "rgba(255,255,255,0.08)", width: "100%" }}>
                                            <div
                                                style={{
                                                    height: "100%",
                                                    width: `${Math.min(100, (p.sample_count / p.target_sample_size) * 100)}%`,
                                                    background: p.sample_count >= p.target_sample_size ? "var(--pos)" : "var(--accent-purple)",
                                                    transition: "width 0.3s ease",
                                                }}
                                            />
                                        </div>
                                    </div>

                                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                                        <div className="mono" style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>
                                            WIN RATE: <span style={{ color: "var(--pos)", fontWeight: 700 }}>{p.win_rate}%</span>
                                        </div>

                                        {p.status !== "PROMOTED" && (
                                            <button
                                                className="mono"
                                                onClick={() => setPromotingPipeline(p)}
                                                disabled={!p.eligible_for_promotion}
                                                style={{
                                                    background: p.eligible_for_promotion ? "rgba(16,185,129,0.15)" : "rgba(255,255,255,0.04)",
                                                    border: p.eligible_for_promotion ? "1px solid var(--pos)" : "1px solid transparent",
                                                    color: p.eligible_for_promotion ? "var(--pos)" : "var(--text-dim)",
                                                    padding: "0.3rem 0.75rem",
                                                    fontSize: "0.7rem",
                                                    fontWeight: 800,
                                                    cursor: p.eligible_for_promotion ? "pointer" : "not-allowed",
                                                    display: "flex",
                                                    alignItems: "center",
                                                    gap: "0.3rem",
                                                }}
                                            >
                                                <ShieldCheck size={12} />
                                                MANUALLY PROMOTE TO LIVE
                                            </button>
                                        )}
                                    </div>
                                </div>
                            ))
                        ) : (
                            <div style={{ color: "var(--text-dim)", fontSize: "0.8rem", fontStyle: "italic", textAlign: "center", padding: "1.5rem" }}>
                                No staged shadow pipelines. Run a walk-forward backtest below and click "Stage to Shadow Mode".
                            </div>
                        )}
                    </div>
                </div>
            </div>

            {/* Section 2: Walk-Forward Candidate Strategy Rankings */}
            <div style={{ background: "var(--bg-card)", border: "1px solid rgba(255,255,255,0.08)", padding: "1.2rem" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                        <Flame size={18} color="var(--accent-purple)" />
                        <h2 style={{ fontSize: "1rem", fontWeight: 800, margin: 0, letterSpacing: "-0.01em" }}>
                            WALK-FORWARD CANDIDATE STRATEGY RANKINGS
                        </h2>
                    </div>

                    <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                        Ranked by <span style={{ color: "var(--accent-purple)", fontWeight: 700 }}>Walk-Forward Consistency</span> & Expectancy
                    </div>
                </div>

                {candidates.length > 0 ? (
                    <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
                        {candidates.map((cand, idx) => {
                            const isExpanded = expandedCandidate === cand.candidate_name;

                            return (
                                <div
                                    key={cand.candidate_name}
                                    style={{
                                        border: "1px solid rgba(255,255,255,0.06)",
                                        background: "rgba(14, 20, 36, 0.6)",
                                    }}
                                >
                                    {/* Candidate Header Row */}
                                    <div
                                        style={{
                                            padding: "0.85rem 1rem",
                                            display: "flex",
                                            justifyContent: "space-between",
                                            alignItems: "center",
                                            background: "rgba(255,255,255,0.02)",
                                            cursor: "pointer",
                                        }}
                                        onClick={() => setExpandedCandidate(isExpanded ? null : cand.candidate_name)}
                                    >
                                        <div style={{ display: "flex", alignItems: "center", gap: "0.8rem" }}>
                                            <span className="mono" style={{ fontSize: "0.85rem", fontWeight: 800, color: "var(--accent-purple)", background: "rgba(168,85,247,0.15)", width: "24px", height: "24px", display: "flex", alignItems: "center", justifyContent: "center" }}>
                                                #{idx + 1}
                                            </span>
                                            <div>
                                                <span style={{ fontWeight: 800, fontSize: "0.9rem", color: "var(--text-strong)" }}>
                                                    {cand.candidate_name}
                                                </span>
                                                <div style={{ display: "flex", gap: "0.5rem", marginTop: "0.2rem" }}>
                                                    <span className="mono" style={{ fontSize: "0.65rem", background: "rgba(168,85,247,0.2)", color: "var(--accent-purple)", padding: "0.1rem 0.4rem", fontWeight: 700 }}>
                                                        l2_approximated: true
                                                    </span>
                                                </div>
                                            </div>
                                        </div>

                                        <div style={{ display: "flex", alignItems: "center", gap: "1.5rem" }}>
                                            <div style={{ textAlign: "right" }}>
                                                <div style={{ fontSize: "0.68rem", color: "var(--text-dim)" }}>WIN RATE</div>
                                                <div className="mono" style={{ fontSize: "0.95rem", fontWeight: 800, color: "var(--pos)" }}>
                                                    {cand.overall_win_rate}%
                                                </div>
                                            </div>

                                            <div style={{ textAlign: "right" }}>
                                                <div style={{ fontSize: "0.68rem", color: "var(--text-dim)" }}>AVG R</div>
                                                <div className="mono" style={{ fontSize: "0.95rem", fontWeight: 800, color: cand.overall_avg_r >= 0 ? "var(--pos)" : "var(--neg)" }}>
                                                    {cand.overall_avg_r > 0 ? `+${cand.overall_avg_r}` : cand.overall_avg_r}R
                                                </div>
                                            </div>

                                            <div style={{ textAlign: "right" }}>
                                                <div style={{ fontSize: "0.68rem", color: "var(--text-dim)" }}>CONSISTENCY</div>
                                                <div className="mono" style={{ fontSize: "0.95rem", fontWeight: 800, color: "var(--accent-amber)" }}>
                                                    {cand.consistency_score}%
                                                </div>
                                            </div>

                                            <div style={{ textAlign: "right" }}>
                                                <div style={{ fontSize: "0.68rem", color: "var(--text-dim)" }}>TRADES</div>
                                                <div className="mono" style={{ fontSize: "0.95rem", fontWeight: 800, color: "var(--text-strong)" }}>
                                                    {cand.overall_trades_count}
                                                </div>
                                            </div>

                                            <button
                                                className="mono"
                                                onClick={(e) => {
                                                    e.stopPropagation();
                                                    handleStageCandidate(cand);
                                                }}
                                                style={{
                                                    background: "rgba(168,85,247,0.15)",
                                                    border: "1px solid rgba(168,85,247,0.4)",
                                                    color: "var(--accent-purple)",
                                                    padding: "0.4rem 0.8rem",
                                                    fontSize: "0.72rem",
                                                    fontWeight: 800,
                                                    cursor: "pointer",
                                                }}
                                            >
                                                STAGE TO SHADOW MODE
                                            </button>

                                            {isExpanded ? <ChevronUp size={18} color="var(--text-dim)" /> : <ChevronDown size={18} color="var(--text-dim)" />}
                                        </div>
                                    </div>

                                    {/* Expanded Walk-Forward Rolling Windows Breakdown */}
                                    {isExpanded && (
                                        <div style={{ padding: "1rem", borderTop: "1px solid rgba(255,255,255,0.06)", background: "rgba(0,0,0,0.2)" }}>
                                            <div style={{ fontSize: "0.75rem", fontWeight: 800, color: "var(--text-muted)", marginBottom: "0.6rem" }}>
                                                ROLLING OUT-OF-SAMPLE WINDOW BREAKDOWN:
                                            </div>

                                            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.75rem" }}>
                                                <thead>
                                                    <tr className="mono" style={{ borderBottom: "1px solid rgba(255,255,255,0.08)", color: "var(--text-dim)", textAlign: "left" }}>
                                                        <th style={{ padding: "0.4rem" }}>WINDOW</th>
                                                        <th style={{ padding: "0.4rem" }}>TEST PERIOD</th>
                                                        <th style={{ padding: "0.4rem" }}>TRADES</th>
                                                        <th style={{ padding: "0.4rem" }}>WIN RATE</th>
                                                        <th style={{ padding: "0.4rem" }}>AVG R</th>
                                                        <th style={{ padding: "0.4rem" }}>MAX DD</th>
                                                        <th style={{ padding: "0.4rem" }}>L2 STATUS</th>
                                                    </tr>
                                                </thead>
                                                <tbody>
                                                    {cand.window_results?.map((w) => (
                                                        <tr key={w.window_index} style={{ borderBottom: "1px solid rgba(255,255,255,0.03)" }}>
                                                            <td className="mono" style={{ padding: "0.4rem", fontWeight: 700 }}>Window #{w.window_index + 1}</td>
                                                            <td className="mono" style={{ padding: "0.4rem", color: "var(--text-muted)" }}>
                                                                {new Date(w.test_start_ts * 1000).toLocaleDateString()} — {new Date(w.test_end_ts * 1000).toLocaleDateString()}
                                                            </td>
                                                            <td className="mono" style={{ padding: "0.4rem", fontWeight: 700 }}>{w.trades_count}</td>
                                                            <td className="mono" style={{ padding: "0.4rem", color: "var(--pos)", fontWeight: 700 }}>{w.win_rate}%</td>
                                                            <td className="mono" style={{ padding: "0.4rem", color: w.avg_r >= 0 ? "var(--pos)" : "var(--neg)", fontWeight: 700 }}>
                                                                {w.avg_r > 0 ? `+${w.avg_r}` : w.avg_r}R
                                                            </td>
                                                            <td className="mono" style={{ padding: "0.4rem", color: "var(--neg)" }}>-{w.max_drawdown_pct}R</td>
                                                            <td style={{ padding: "0.4rem" }}>
                                                                <span className="mono" style={{ fontSize: "0.65rem", background: "rgba(168,85,247,0.15)", color: "var(--accent-purple)", padding: "0.1rem 0.35rem" }}>
                                                                    l2_approximated
                                                                </span>
                                                            </td>
                                                        </tr>
                                                    ))}
                                                </tbody>
                                            </table>
                                        </div>
                                    )}
                                </div>
                            );
                        })}
                    </div>
                ) : (
                    <div style={{ textAlign: "center", padding: "3rem", color: "var(--text-dim)", fontStyle: "italic" }}>
                        Click "RUN WALK-FORWARD BACKTEST" above to execute rolling window validation across candidate strategies.
                    </div>
                )}
            </div>

            {/* Manual Promotion Explicit Confirmation Modal */}
            {promotingPipeline && (
                <div
                    style={{
                        position: "fixed",
                        top: 0,
                        left: 0,
                        right: 0,
                        bottom: 0,
                        background: "rgba(0,0,0,0.8)",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        zIndex: 9999,
                    }}
                >
                    <div
                        style={{
                            background: "var(--bg-card)",
                            border: "1px solid var(--pos)",
                            maxWidth: "500px",
                            width: "90%",
                            padding: "1.5rem",
                            boxShadow: "0 20px 25px -5px rgba(0, 0, 0, 0.5)",
                        }}
                    >
                        <div style={{ display: "flex", alignItems: "center", gap: "0.6rem", color: "var(--pos)", marginBottom: "1rem" }}>
                            <ShieldCheck size={24} />
                            <h3 style={{ margin: 0, fontSize: "1.1rem", fontWeight: 800 }}>
                                CONFIRM MANUAL STRATEGY PROMOTION
                            </h3>
                        </div>

                        <p style={{ fontSize: "0.85rem", color: "var(--text-strong)", lineHeight: 1.5 }}>
                            You are explicitly promoting shadow pipeline version{" "}
                            <span className="mono" style={{ color: "var(--accent-purple)", fontWeight: 800 }}>
                                {promotingPipeline.pipeline_version}
                            </span>{" "}
                            (<span style={{ fontWeight: 700 }}>{promotingPipeline.candidate_name}</span>) to live capital status.
                        </p>

                        <div style={{ background: "rgba(16,185,129,0.08)", padding: "0.75rem", borderLeft: "3px solid var(--pos)", marginBottom: "1.2rem", fontSize: "0.78rem" }}>
                            <div className="mono" style={{ fontWeight: 700, color: "var(--pos)", marginBottom: "0.2rem" }}>
                                SHADOW SAMPLE THRESHOLD SATISFIED:
                            </div>
                            <div style={{ color: "var(--text-muted)" }}>
                                {promotingPipeline.sample_count} closed shadow trades accumulated (minimum required: {promotingPipeline.target_sample_size}).
                            </div>
                        </div>

                        <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.8rem" }}>
                            <button
                                className="mono"
                                onClick={() => setPromotingPipeline(null)}
                                disabled={promoting}
                                style={{
                                    background: "rgba(255,255,255,0.05)",
                                    border: "1px solid rgba(255,255,255,0.1)",
                                    color: "var(--text-muted)",
                                    padding: "0.5rem 1rem",
                                    fontSize: "0.78rem",
                                    cursor: "pointer",
                                }}
                            >
                                CANCEL
                            </button>

                            <button
                                className="mono"
                                onClick={handleConfirmPromotion}
                                disabled={promoting}
                                style={{
                                    background: "var(--pos)",
                                    border: "none",
                                    color: "#000",
                                    padding: "0.5rem 1.2rem",
                                    fontSize: "0.78rem",
                                    fontWeight: 800,
                                    cursor: "pointer",
                                    display: "flex",
                                    alignItems: "center",
                                    gap: "0.4rem",
                                }}
                            >
                                {promoting ? <RefreshCw size={14} className="spin" /> : <ShieldCheck size={14} />}
                                CONFIRM MANUAL PROMOTION
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};
