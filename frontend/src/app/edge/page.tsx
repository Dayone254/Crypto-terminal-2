"use client";

import React, { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import {
    Activity, TrendingUp, TrendingDown, Clock, Target, ShieldAlert,
    Crosshair, Zap, Trophy, Filter, RefreshCw, Eye, ExternalLink, X
} from "lucide-react";
import { NativeChart } from "@/components/NativeChart";
import { API_BASE } from "@/lib/api";

const API = `${API_BASE}/api/v1/backtest`;

// ── Types ──────────────────────────────────────────────────────────────────────
interface Stats {
    win_rate: number; total_closed: number; wins: number;
    losses: number; pending_count: number;
}

interface Trade {
    id: number; symbol: string; timestamp: number; score: number;
    label: string; entry_price: number; tp_price: number; sl_price: number;
    status: "WIN" | "LOSS" | "PENDING" | "PARTIAL_WIN" | "BREAK_EVEN" | "ACTIVE_T2"; mfe: number; mae: number;
    closed_at: number | null; filled_at: number | null; fill_price: number | null;
}

interface SymbolStat {
    symbol: string; wins: number; losses: number; pending: number;
    total: number; win_rate: number | null; avg_score: number | null;
    avg_mfe: number | null; avg_mae: number | null;
}

// ── Helpers ────────────────────────────────────────────────────────────────────
const fmt = (n: number) => n.toLocaleString("en-US", { minimumFractionDigits: 4, maximumFractionDigits: 4 });
const fmtDate = (ts: number) => ts ? new Date(ts * 1000).toLocaleString("en-GB", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }) : "─";

const statusStyle = (status: string, filled: boolean): React.CSSProperties => ({
    WIN: { color: "#10B981", background: "rgba(16,185,129,0.12)", border: "none" },
    PARTIAL_WIN: { color: "#34D399", background: "rgba(52,211,153,0.12)", border: "none" },
    LOSS: { color: "#F43F5E", background: "rgba(244,63,94,0.12)", border: "none" },
    BREAK_EVEN: { color: "#94A3B8", background: "rgba(148,163,184,0.12)", border: "none" },
    ACTIVE_T2: { color: "#3B82F6", background: "rgba(59,130,246,0.12)", border: "none" },
    // PENDING splits into WAITING (no fill) vs IN TRADE (filled, hunting T1)
    PENDING: filled
        ? { color: "#F59E0B", background: "rgba(245,158,11,0.18)", border: "1px solid rgba(245,158,11,0.4)" }
        : { color: "#64748B", background: "rgba(100,116,139,0.1)", border: "none" },
}[status] || { color: "#E2E8F0", background: "rgba(255,255,255,0.05)", border: "none" });

const statusLabel = (status: string, filled: boolean): string => ({
    WIN: "WIN ✓", PARTIAL_WIN: "PARTIAL WIN", LOSS: "LOSS ✗",
    BREAK_EVEN: "BREAK EVEN", ACTIVE_T2: "ACTIVE T2 →",
    PENDING: filled ? "IN TRADE ▶" : "WAITING",
}[status] ?? status);

// ── Stat Card ──────────────────────────────────────────────────────────────────
const StatCard: React.FC<{ label: string; value: string | number; sub?: string; color?: string; icon: React.ReactNode }> = ({ label, value, sub, color = "#E2E8F0", icon }) => (
    <div style={{ background: "#0B0F19", border: "none", borderRadius: "10px", padding: "1.1rem 1.3rem", display: "flex", flexDirection: "column", gap: "0.4rem" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", color: "var(--text-dim)", fontSize: "0.65rem", fontWeight: 800, textTransform: "uppercase", letterSpacing: "0.05em" }}>
            {icon}{label}
        </div>
        <div style={{ fontSize: "1.8rem", fontWeight: 900, color, fontFamily: "var(--font-jetbrains)", lineHeight: 1 }}>{value}</div>
        {sub && <div style={{ fontSize: "0.7rem", color: "var(--text-dim)" }}>{sub}</div>}
    </div>
);

// ── Win-Rate Ring ──────────────────────────────────────────────────────────────
const WinRateRing: React.FC<{ rate: number }> = ({ rate }) => {
    const r = 54, circ = 2 * Math.PI * r;
    const offset = circ - (circ * rate) / 100;
    const color = rate >= 60 ? "#10B981" : rate >= 45 ? "#F59E0B" : "#F43F5E";
    return (
        <div style={{ position: "relative", width: 140, height: 140, flexShrink: 0 }}>
            <svg width={140} height={140} viewBox="0 0 140 140">
                <circle cx={70} cy={70} r={r} fill="none" stroke="rgba(255,255,255,0.05)" strokeWidth={14} />
                <circle cx={70} cy={70} r={r} fill="none" stroke={color} strokeWidth={14}
                    strokeDasharray={circ} strokeDashoffset={offset} strokeLinecap="round"
                    transform="rotate(-90 70 70)" style={{ transition: "stroke-dashoffset 1.2s ease-out" }} />
            </svg>
            <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" }}>
                <span style={{ fontSize: "1.6rem", fontWeight: 900, color, fontFamily: "var(--font-jetbrains)" }}>{rate.toFixed(0)}%</span>
                <span style={{ fontSize: "0.55rem", color: "var(--text-dim)", textTransform: "uppercase", letterSpacing: "0.06em", fontWeight: 800 }}>Win Rate</span>
            </div>
        </div>
    );
};

// ── Main Page ──────────────────────────────────────────────────────────────────
export default function EdgePage() {
    const [stats, setStats] = useState<Stats | null>(null);
    const [trades, setTrades] = useState<Trade[]>([]);
    const [symbols, setSymbols] = useState<SymbolStat[]>([]);
    const [filterStatus, setFilterStatus] = useState<string>("ALL");
    const [filterSymbol, setFilterSymbol] = useState<string>("");
    const [loading, setLoading] = useState(true);
    const [activeTab, setActiveTab] = useState<"trades" | "symbols">("trades");
    const [selectedTrade, setSelectedTrade] = useState<Trade | null>(null);

    const load = useCallback(async () => {
        setLoading(true);
        try {
            const [s, t, sym] = await Promise.all([
                fetch(`${API}/stats`).then(r => r.json()),
                fetch(`${API}/trades?limit=200${filterStatus !== "ALL" ? `&status=${filterStatus}` : ""}${filterSymbol ? `&symbol=${filterSymbol}` : ""}`).then(r => r.json()),
                fetch(`${API}/symbols`).then(r => r.json()),
            ]);
            setStats(s);
            setTrades(t.trades || []);
            setSymbols(sym.symbols || []);
        } catch { } finally {
            setLoading(false);
        }
    }, [filterStatus, filterSymbol]);

    useEffect(() => { load(); }, [load]);
    useEffect(() => { const i = setInterval(load, 30000); return () => clearInterval(i); }, [load]);

    return (
        <div style={{ minHeight: "100vh", display: "flex", flexDirection: "column", background: "var(--bg-dark)", color: "#E2E8F0" }}>

            {/* ── Header ── */}
            <header style={{ padding: "0.75rem 1.5rem", borderBottom: "none", background: "#080A0F", display: "flex", alignItems: "center", justifyContent: "space-between", flexShrink: 0 }}>
                <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
                    <Link href="/" style={{ display: "flex", alignItems: "center", gap: "0.5rem", textDecoration: "none" }}>
                        <div style={{ background: "rgba(6,182,212,0.15)", border: "none", padding: "0.3rem", borderRadius: "6px", display: "flex" }}>
                            <Zap size={16} color="#06B6D4" fill="#06B6D4" />
                        </div>
                        <span style={{ fontSize: "0.75rem", fontWeight: 800, color: "var(--text-muted)", letterSpacing: "0.05em" }}>TOP PICKER TERMINAL</span>
                    </Link>
                    <span style={{ color: "var(--panel-border)" }}>|</span>
                    <div style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                        <Activity size={14} color="#06B6D4" />
                        <span style={{ fontSize: "0.8rem", fontWeight: 800, color: "#E2E8F0", letterSpacing: "0.03em" }}>STATISTICAL EDGE TRACKER</span>
                    </div>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
                    <button onClick={load} disabled={loading} style={{ background: "rgba(255,255,255,0.04)", border: "none", color: "var(--text-muted)", padding: "0.35rem 0.75rem", borderRadius: "6px", cursor: "pointer", display: "flex", alignItems: "center", gap: "0.35rem", fontSize: "0.72rem", fontWeight: 700 }}>
                        <RefreshCw size={12} style={{ animation: loading ? "spin 1s linear infinite" : "none" }} /> REFRESH
                    </button>
                    <Link href="/" style={{ background: "rgba(255,255,255,0.04)", border: "none", color: "var(--text-muted)", padding: "0.35rem 0.8rem", borderRadius: "6px", fontSize: "0.72rem", fontWeight: 700, textDecoration: "none" }}>
                        ← SCANNER
                    </Link>
                </div>
            </header>

            <main style={{ flex: 1, padding: "1.5rem", display: "flex", flexDirection: "column", gap: "1.5rem" }}>

                {/* ── Top Stats Bar ── */}
                {stats && (
                    <div style={{ display: "grid", gridTemplateColumns: "auto 1fr 1fr 1fr 1fr 1fr", gap: "1rem", alignItems: "stretch" }}>
                        {/* Ring */}
                        <div style={{ background: "#0B0F19", border: "none", borderRadius: "10px", padding: "1rem 1.5rem", display: "flex", alignItems: "center", gap: "1.5rem" }}>
                            <WinRateRing rate={stats.win_rate} />
                            <div style={{ display: "flex", flexDirection: "column", gap: "0.6rem" }}>
                                <div style={{ fontSize: "0.65rem", color: "var(--text-dim)", textTransform: "uppercase", letterSpacing: "0.05em", fontWeight: 800 }}>System Edge</div>
                                <div style={{ display: "flex", gap: "1rem" }}>
                                    <div><div style={{ fontSize: "0.6rem", color: "var(--text-dim)", textTransform: "uppercase" }}>Wins</div><div style={{ fontSize: "1.2rem", fontWeight: 900, color: "#10B981", fontFamily: "var(--font-jetbrains)" }}>{stats.wins}</div></div>
                                    <div><div style={{ fontSize: "0.6rem", color: "var(--text-dim)", textTransform: "uppercase" }}>Losses</div><div style={{ fontSize: "1.2rem", fontWeight: 900, color: "#F43F5E", fontFamily: "var(--font-jetbrains)" }}>{stats.losses}</div></div>
                                    <div><div style={{ fontSize: "0.6rem", color: "var(--text-dim)", textTransform: "uppercase" }}>Pending</div><div style={{ fontSize: "1.2rem", fontWeight: 900, color: "#F59E0B", fontFamily: "var(--font-jetbrains)" }}>{stats.pending_count}</div></div>
                                </div>
                            </div>
                        </div>
                        <StatCard icon={<Activity size={12} />} label="Total Signals" value={stats.total_closed + stats.pending_count} sub="All-time logged setups" />
                        <StatCard icon={<TrendingUp size={12} />} label="Closed Trades" value={stats.total_closed} sub="WIN + LOSS evaluated" color="#06B6D4" />
                        <StatCard icon={<Trophy size={12} />} label="Win Rate" value={`${stats.win_rate.toFixed(1)}%`} sub={`${stats.wins}W / ${stats.losses}L record`} color={stats.win_rate >= 50 ? "#10B981" : "#F59E0B"} />
                        <StatCard icon={<Clock size={12} />} label="Active Tests" value={stats.pending_count} sub="Forward-testing now" color="#F59E0B" />
                        <StatCard icon={<Filter size={12} />} label="Unique Symbols" value={symbols.length} sub="In the edge ledger" color="#A78BFA" />
                    </div>
                )}

                {/* ── Tabs + Filters ── */}
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "1rem", flexWrap: "wrap" }}>
                    {/* Tab switcher */}
                    <div style={{ display: "flex", gap: "0.5rem" }}>
                        {(["trades", "symbols"] as const).map(tab => (
                            <button key={tab} onClick={() => setActiveTab(tab)} style={{
                                padding: "0.5rem 1rem", borderRadius: "7px", border: "1px solid",
                                fontWeight: 800, fontSize: "0.75rem", cursor: "pointer", textTransform: "uppercase", letterSpacing: "0.04em",
                                background: activeTab === tab ? "rgba(6,182,212,0.15)" : "transparent",
                                borderColor: activeTab === tab ? "rgba(6,182,212,0.4)" : "var(--panel-border)",
                                color: activeTab === tab ? "#06B6D4" : "var(--text-muted)",
                            }}>
                                {tab === "trades" ? `Trade Ledger (${trades.length})` : `Symbol Leaderboard (${symbols.length})`}
                            </button>
                        ))}
                    </div>

                    {/* Filters — only show on trades tab */}
                    {activeTab === "trades" && (
                        <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
                            {["ALL", "PENDING", "ACTIVE_T2", "WIN", "PARTIAL_WIN", "LOSS", "BREAK_EVEN"].map(s => (
                                <button key={s} onClick={() => setFilterStatus(s)} style={{
                                    padding: "0.35rem 0.7rem", borderRadius: "6px", border: "1px solid",
                                    fontWeight: 800, fontSize: "0.68rem", cursor: "pointer",
                                    background: filterStatus === s ? "rgba(6,182,212,0.1)" : "transparent",
                                    borderColor: filterStatus === s ? "rgba(6,182,212,0.35)" : "var(--panel-border)",
                                    color: filterStatus === s ? "#06B6D4" : "var(--text-dim)",
                                }}>
                                    {s === "PENDING" ? "PENDING (Tagged)" : s === "ACTIVE_T2" ? "ACTIVE T2" : s}
                                </button>
                            ))}
                            <input
                                type="text" placeholder="Filter symbol..."
                                value={filterSymbol}
                                onChange={e => setFilterSymbol(e.target.value.toUpperCase())}
                                style={{ background: "rgba(255,255,255,0.04)", border: "none", borderRadius: "6px", padding: "0.35rem 0.7rem", color: "#E2E8F0", fontSize: "0.75rem", outline: "none", fontFamily: "var(--font-jetbrains)", width: "140px" }}
                            />
                        </div>
                    )}
                </div>

                {/* ── Trade Ledger Table ── */}
                {activeTab === "trades" && (
                    <div style={{ background: "#080A0F", border: "none", borderRadius: "12px", overflow: "hidden", flex: 1 }}>
                        {/* Table Header */}
                        <div style={{ display: "grid", gridTemplateColumns: "1.8fr 0.9fr 0.8fr 1.4fr 1.2fr 1.2fr 1.2fr 0.9fr 0.9fr 0.9fr 1.4fr 1.4fr", gap: "0.5rem", padding: "0.65rem 1.1rem", background: "#0B0F19", borderBottom: "none", fontSize: "0.58rem", fontWeight: 800, color: "var(--text-dim)", textTransform: "uppercase", letterSpacing: "0.05em" }}>
                            <span>Symbol</span><span>Label</span><span>Score</span>
                            <span>Zone Price</span><span>TP</span><span>SL</span>
                            <span style={{ color: "#F59E0B" }}>Fill Price</span>
                            <span>Status</span><span>MFE</span><span>MAE</span>
                            <span>Signal Fired</span><span>Filled / Closed</span>
                        </div>

                        {/* Rows */}
                        <div style={{ overflowY: "auto", maxHeight: "calc(100vh - 380px)" }}>
                            {trades.length === 0 ? (
                                <div style={{ padding: "3rem", textAlign: "center", color: "var(--text-dim)", fontSize: "0.85rem" }}>
                                    No trades found.{stats?.pending_count === 0 ? " The scanner will log the next ENTRY_ZONE or COILED setup automatically." : ""}
                                </div>
                            ) : trades.map(t => (
                                <div key={t.id}
                                    onClick={() => setSelectedTrade(t)}
                                    style={{ display: "grid", gridTemplateColumns: "1.8fr 0.9fr 0.8fr 1.4fr 1.2fr 1.2fr 1.2fr 0.9fr 0.9fr 0.9fr 1.4fr 1.4fr", gap: "0.5rem", padding: "0.65rem 1.1rem", borderBottom: "none", alignItems: "center", cursor: "pointer", transition: "background 0.15s" }}
                                    onMouseEnter={e => (e.currentTarget.style.background = "rgba(6, 182, 212, 0.08)")}
                                    onMouseLeave={e => (e.currentTarget.style.background = "transparent")}>
                                    <div style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                                        <span style={{ fontWeight: 800, color: "#E2E8F0", fontSize: "0.82rem" }}>
                                            {t.symbol}
                                        </span>
                                        <span style={{ fontSize: "0.6rem", color: "#06B6D4", background: "rgba(6,182,212,0.15)", padding: "0.1rem 0.3rem", borderRadius: "4px", fontWeight: 700 }}>
                                            INSPECT 🔍
                                        </span>
                                    </div>
                                    <span style={{ fontSize: "0.62rem", fontWeight: 800, color: t.label === "ENTRY_ZONE" ? "#10B981" : "#06B6D4" }}>{t.label}</span>
                                    <span className="mono" style={{ fontSize: "0.78rem", color: "#E2E8F0" }}>{t.score?.toFixed(0)}</span>

                                    {/* Prices */}
                                    <span className="mono" style={{ fontSize: "0.72rem", color: "#06B6D4" }}>${fmt(t.entry_price)}</span>
                                    <span className="mono" style={{ fontSize: "0.72rem", color: "#10B981" }}>${fmt(t.tp_price)}</span>
                                    <span className="mono" style={{ fontSize: "0.72rem", color: "#F43F5E" }}>${fmt(t.sl_price)}</span>

                                    {/* Fill Price — highlight if filled vs pending entry */}
                                    <div style={{ display: "flex", flexDirection: "column", gap: "1px" }}>
                                        {t.fill_price ? (
                                            <span className="mono" style={{ fontSize: "0.72rem", color: "#F59E0B", fontWeight: 800 }}>${fmt(t.fill_price)}</span>
                                        ) : t.status === "PENDING" ? (
                                            <span style={{ fontSize: "0.65rem", color: "rgba(245,158,11,0.5)", fontStyle: "italic" }}>Pending Fill</span>
                                        ) : (
                                            <span className="mono" style={{ fontSize: "0.72rem", color: "#F59E0B", fontWeight: 800 }}>${fmt(t.entry_price)}</span>
                                        )}
                                    </div>

                                    <span style={{ ...statusStyle(t.status, !!t.filled_at), padding: "0.15rem 0.45rem", borderRadius: "5px", fontSize: "0.58rem", fontWeight: 800, textAlign: "center", whiteSpace: "nowrap" }}>
                                        {statusLabel(t.status, !!t.filled_at)}
                                    </span>
                                    <span className="mono" style={{ fontSize: "0.7rem", color: t.mfe > 0 ? "#10B981" : "var(--text-dim)" }}>{t.mfe ? `+${t.mfe.toFixed(2)}%` : "─"}</span>
                                    <span className="mono" style={{ fontSize: "0.7rem", color: t.mae < 0 ? "#F43F5E" : "var(--text-dim)" }}>{t.mae ? `${t.mae.toFixed(2)}%` : "─"}</span>

                                    {/* Timestamps */}
                                    <div style={{ display: "flex", flexDirection: "column", gap: "2px" }}>
                                        <span style={{ fontSize: "0.62rem", color: "var(--text-dim)" }}>{fmtDate(t.timestamp)}</span>
                                    </div>
                                    <div style={{ display: "flex", flexDirection: "column", gap: "2px" }}>
                                        {t.filled_at && <span style={{ fontSize: "0.62rem", color: "#F59E0B" }}>▶ {fmtDate(t.filled_at)}</span>}
                                        {t.closed_at && <span style={{ fontSize: "0.62rem", color: (t.status === "WIN" || t.status === "PARTIAL_WIN") ? "#10B981" : t.status === "BREAK_EVEN" ? "#94A3B8" : "#F43F5E" }}>✕ {fmtDate(t.closed_at)}</span>}
                                        {!t.filled_at && !t.closed_at && <span style={{ fontSize: "0.62rem", color: "rgba(255,255,255,0.2)", fontStyle: "italic" }}>Pending fill</span>}
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>
                )}

                {/* ── Symbol Leaderboard ── */}
                {activeTab === "symbols" && (
                    <div style={{ background: "#080A0F", border: "none", borderRadius: "12px", overflow: "hidden", flex: 1 }}>
                        <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr 1fr 1fr 1fr 1.5fr 1.5fr 1.5fr", gap: "0.5rem", padding: "0.65rem 1.1rem", background: "#0B0F19", borderBottom: "none", fontSize: "0.6rem", fontWeight: 800, color: "var(--text-dim)", textTransform: "uppercase", letterSpacing: "0.05em" }}>
                            <span>Symbol</span><span>Wins</span><span>Losses</span><span>Pending</span><span>Total</span><span>Win Rate</span><span>Avg MFE</span><span>Avg Score</span>
                        </div>
                        <div style={{ overflowY: "auto", maxHeight: "calc(100vh - 380px)" }}>
                            {symbols.length === 0 ? (
                                <div style={{ padding: "3rem", textAlign: "center", color: "var(--text-dim)", fontSize: "0.85rem" }}>No symbol data yet — the system logs setups autonomously as the scanner runs.</div>
                            ) : symbols.map((s, i) => (
                                <div key={s.symbol} style={{ display: "grid", gridTemplateColumns: "2fr 1fr 1fr 1fr 1fr 1.5fr 1.5fr 1.5fr", gap: "0.5rem", padding: "0.7rem 1.1rem", borderBottom: "none", alignItems: "center" }}
                                    onMouseEnter={e => (e.currentTarget.style.background = "rgba(255,255,255,0.02)")}
                                    onMouseLeave={e => (e.currentTarget.style.background = "transparent")}>
                                    <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
                                        <span style={{ fontWeight: 800, fontSize: "0.65rem", color: i < 3 ? ["#F59E0B", "#94A3B8", "#CD7F32"][i] : "var(--text-dim)", width: "18px", textAlign: "center" }}>
                                            {i === 0 ? "🥇" : i === 1 ? "🥈" : i === 2 ? "🥉" : `#${i + 1}`}
                                        </span>
                                        <Link href={`/market/${s.symbol}`} style={{ fontWeight: 800, color: "#E2E8F0", fontSize: "0.82rem", textDecoration: "none" }}
                                            onMouseEnter={e => (e.currentTarget.style.color = "#06B6D4")}
                                            onMouseLeave={e => (e.currentTarget.style.color = "#E2E8F0")}>
                                            {s.symbol}
                                        </Link>
                                    </div>
                                    <span className="mono" style={{ color: "#10B981", fontWeight: 800 }}>{s.wins}</span>
                                    <span className="mono" style={{ color: "#F43F5E", fontWeight: 800 }}>{s.losses}</span>
                                    <span className="mono" style={{ color: "#F59E0B" }}>{s.pending}</span>
                                    <span className="mono" style={{ color: "var(--text-muted)" }}>{s.total}</span>
                                    <div style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                                        <div style={{ flex: 1, height: "4px", background: "rgba(255,255,255,0.06)", borderRadius: "2px", overflow: "hidden" }}>
                                            {s.win_rate !== null && <div style={{ width: `${s.win_rate}%`, height: "100%", background: s.win_rate >= 60 ? "#10B981" : s.win_rate >= 45 ? "#F59E0B" : "#F43F5E", borderRadius: "2px", transition: "width 0.6s ease" }} />}
                                        </div>
                                        <span className="mono" style={{ fontSize: "0.75rem", fontWeight: 800, color: s.win_rate === null ? "var(--text-dim)" : s.win_rate >= 60 ? "#10B981" : s.win_rate >= 45 ? "#F59E0B" : "#F43F5E" }}>
                                            {s.win_rate !== null ? `${s.win_rate}%` : "─"}
                                        </span>
                                    </div>
                                    <span className="mono" style={{ fontSize: "0.75rem", color: s.avg_mfe && s.avg_mfe > 0 ? "#10B981" : "var(--text-dim)" }}>
                                        {s.avg_mfe ? `+${s.avg_mfe.toFixed(2)}%` : "─"}
                                    </span>
                                    <span className="mono" style={{ fontSize: "0.75rem", color: "#06B6D4" }}>
                                        {s.avg_score ? s.avg_score.toFixed(0) : "─"}
                                    </span>
                                </div>
                            ))}
                        </div>
                    </div>
                )}
            </main>

            {/* ── Trade Visual Inspector Modal ── */}
            {selectedTrade && (
                <div style={{
                    position: "fixed", inset: 0, zIndex: 9999,
                    background: "rgba(5, 7, 13, 0.85)", backdropFilter: "blur(8px)",
                    display: "flex", alignItems: "center", justifyContent: "center", padding: "1.5rem"
                }}>
                    <div style={{
                        background: "#0B0F19", border: "none",
                        borderRadius: "16px", width: "100%", maxWidth: "1250px", maxHeight: "94vh",
                        display: "flex", flexDirection: "column", overflow: "hidden", boxShadow: "0 25px 50px -12px rgba(0, 0, 0, 0.7)"
                    }}>
                        {/* Top Modal Header */}
                        <div style={{
                            padding: "1rem 1.5rem", background: "#080A0F", borderBottom: "none",
                            display: "flex", alignItems: "center", justifyContent: "space-between", flexShrink: 0
                        }}>
                            <div style={{ display: "flex", alignItems: "center", gap: "0.8rem", flexWrap: "wrap" }}>
                                <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                                    <Eye size={18} color="#06B6D4" />
                                    <span style={{ fontSize: "1.1rem", fontWeight: 900, color: "#FFF", fontFamily: "var(--font-jetbrains)" }}>
                                        {selectedTrade.symbol}
                                    </span>
                                </div>

                                {/* Trade Direction Badge */}
                                <span style={{
                                    padding: "0.2rem 0.55rem", borderRadius: "5px", fontSize: "0.65rem", fontWeight: 800,
                                    background: selectedTrade.sl_price > selectedTrade.entry_price ? "rgba(244,63,94,0.18)" : "rgba(16,185,129,0.18)",
                                    color: selectedTrade.sl_price > selectedTrade.entry_price ? "#F43F5E" : "#10B981",
                                    border: selectedTrade.sl_price > selectedTrade.entry_price ? "1px solid rgba(244,63,94,0.3)" : "1px solid rgba(16,185,129,0.3)"
                                }}>
                                    {selectedTrade.sl_price > selectedTrade.entry_price ? "SHORT" : "LONG"}
                                </span>

                                <span style={{ padding: "0.2rem 0.55rem", borderRadius: "5px", fontSize: "0.65rem", fontWeight: 800, background: "rgba(6,182,212,0.12)", color: "#06B6D4", border: "none" }}>
                                    {selectedTrade.label}
                                </span>

                                <span style={{ ...statusStyle(selectedTrade.status, !!selectedTrade.filled_at), padding: "0.2rem 0.65rem", borderRadius: "5px", fontSize: "0.65rem", fontWeight: 900 }}>
                                    {selectedTrade.status === "WIN" ? "✓ WIN (TARGET HIT)" : selectedTrade.status === "LOSS" ? "✕ LOSS (STOPPED OUT)" : "⏳ PENDING FILL"}
                                </span>
                            </div>

                            <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
                                <Link
                                    href={`/market/${selectedTrade.symbol}`}
                                    target="_blank"
                                    style={{
                                        background: "rgba(6, 182, 212, 0.15)", border: "none",
                                        color: "#06B6D4", padding: "0.4rem 0.85rem", borderRadius: "6px",
                                        fontSize: "0.72rem", fontWeight: 800, textDecoration: "none",
                                        display: "flex", alignItems: "center", gap: "0.4rem"
                                    }}
                                >
                                    <ExternalLink size={14} /> LIVE MARKET DESK
                                </Link>
                                <button
                                    onClick={() => setSelectedTrade(null)}
                                    style={{
                                        background: "rgba(255,255,255,0.05)", border: "none",
                                        color: "var(--text-muted)", padding: "0.4rem 0.75rem", borderRadius: "6px",
                                        cursor: "pointer", fontSize: "0.75rem", fontWeight: 800, display: "flex", alignItems: "center", gap: "0.3rem"
                                    }}
                                >
                                    <X size={14} /> CLOSE
                                </button>
                            </div>
                        </div>

                        {/* Sub-Header HUD Execution Stats */}
                        <div style={{ padding: "0.75rem 1.5rem", background: "rgba(255,255,255,0.015)", borderBottom: "none", display: "flex", alignItems: "center", justifyContent: "space-between", gap: "1rem", flexWrap: "wrap" }}>
                            <div style={{ display: "flex", alignItems: "center", gap: "1.5rem" }}>
                                <div>
                                    <div style={{ fontSize: "0.58rem", color: "var(--text-dim)", textTransform: "uppercase", fontWeight: 800 }}>Entry Zone</div>
                                    <div className="mono" style={{ fontSize: "0.88rem", fontWeight: 800, color: "#06B6D4" }}>${fmt(selectedTrade.entry_price)}</div>
                                </div>
                                <div>
                                    <div style={{ fontSize: "0.58rem", color: "var(--text-dim)", textTransform: "uppercase", fontWeight: 800 }}>Take Profit (TP)</div>
                                    <div className="mono" style={{ fontSize: "0.88rem", fontWeight: 800, color: "#10B981" }}>${fmt(selectedTrade.tp_price)}</div>
                                </div>
                                <div>
                                    <div style={{ fontSize: "0.58rem", color: "var(--text-dim)", textTransform: "uppercase", fontWeight: 800 }}>Stop Loss (SL)</div>
                                    <div className="mono" style={{ fontSize: "0.88rem", fontWeight: 800, color: "#F43F5E" }}>${fmt(selectedTrade.sl_price)}</div>
                                </div>
                                <div>
                                    <div style={{ fontSize: "0.58rem", color: "var(--text-dim)", textTransform: "uppercase", fontWeight: 800 }}>Fill Price</div>
                                    <div className="mono" style={{ fontSize: "0.88rem", fontWeight: 800, color: "#F59E0B" }}>
                                        {selectedTrade.fill_price ? `$${fmt(selectedTrade.fill_price)}` : selectedTrade.status === "PENDING" ? "Pending Fill" : `$${fmt(selectedTrade.entry_price)}`}
                                    </div>
                                </div>
                            </div>

                            <div style={{ display: "flex", alignItems: "center", gap: "1.5rem" }}>
                                <div>
                                    <div style={{ fontSize: "0.58rem", color: "var(--text-dim)", textTransform: "uppercase", fontWeight: 800 }}>Max Gain (MFE)</div>
                                    <div className="mono" style={{ fontSize: "0.88rem", fontWeight: 800, color: selectedTrade.mfe > 0 ? "#10B981" : "var(--text-dim)" }}>
                                        {selectedTrade.mfe ? `+${selectedTrade.mfe.toFixed(2)}%` : "0.00%"}
                                    </div>
                                </div>
                                <div>
                                    <div style={{ fontSize: "0.58rem", color: "var(--text-dim)", textTransform: "uppercase", fontWeight: 800 }}>Max Drawdown (MAE)</div>
                                    <div className="mono" style={{ fontSize: "0.88rem", fontWeight: 800, color: selectedTrade.mae < 0 ? "#F43F5E" : "var(--text-dim)" }}>
                                        {selectedTrade.mae ? `${selectedTrade.mae.toFixed(2)}%` : "0.00%"}
                                    </div>
                                </div>
                                <div>
                                    <div style={{ fontSize: "0.58rem", color: "var(--text-dim)", textTransform: "uppercase", fontWeight: 800 }}>Signal Date</div>
                                    <div style={{ fontSize: "0.78rem", fontWeight: 700, color: "var(--text-muted)" }}>
                                        {fmtDate(selectedTrade.timestamp)}
                                    </div>
                                </div>
                            </div>
                        </div>

                        {/* Interactive Chart Canvas with positionTool overlay */}
                        <div style={{ flex: 1, padding: "1rem", overflow: "hidden", minHeight: "500px" }}>
                            <NativeChart
                                productId={selectedTrade.symbol}
                                height="500px"
                                entryLevel={selectedTrade.entry_price}
                                tpLevel={selectedTrade.tp_price}
                                slLevel={selectedTrade.sl_price}
                                tradeTimestamp={selectedTrade.timestamp}
                                tradeDirection={selectedTrade.sl_price > selectedTrade.entry_price ? "SHORT" : "LONG"}
                            />
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
