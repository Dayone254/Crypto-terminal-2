"use client";

import React, { useCallback, useEffect, useState } from "react";
import { Activity, RefreshCw, Zap, TrendingUp, Code2, Newspaper } from "lucide-react";
import { apiFetch } from "@/lib/api";

// ─── Types ────────────────────────────────────────────────────────────────────
export interface CatalystSignalRow {
    symbol: string;
    coin_id: string;
    catalyst_score: number;
    priority_tier: "CRITICAL" | "HIGH" | "WATCH" | "NOISE";
    volume_surge_ratio: number;
    volume_surge_score: number;
    dev_activity_score: number;
    news_score: number;
    github_stars_score: number;
    commit_count_4w: number;
    pr_merged_4w: number;
    github_stars: number;
    top_headline: string | null;
    catalyst_keywords: string[];
    scorer_boost: number;
    scraped_at: string | null;
    expires_at: string | null;
}

interface CatalystFeedResponse {
    generated_at: string;
    total_signals: number;
    min_tier_filter: string;
    signals: CatalystSignalRow[];
}

// ─── API helpers ─────────────────────────────────────────────────────────────
async function fetchCatalystFeed(minTier = "HIGH"): Promise<CatalystFeedResponse> {
    const res = await apiFetch(`/api/v1/catalyst/feed?min_tier=${minTier}&limit=30`);
    if (!res.ok) throw new Error(`Catalyst feed fetch failed: ${res.status}`);
    return res.json();
}

async function triggerCatalystRefresh(): Promise<void> {
    await apiFetch("/api/v1/catalyst/refresh", { method: "POST" });
}

// ─── Tier config ──────────────────────────────────────────────────────────────
const TIER_CONFIG: Record<string, { label: string; color: string; bg: string; glow: string }> = {
    CRITICAL: {
        label: "CRITICAL",
        color: "var(--neg)",
        bg: "rgba(244,63,94,0.12)",
        glow: "0 0 12px rgba(244,63,94,0.35)",
    },
    HIGH: {
        label: "HIGH",
        color: "var(--accent-amber)",
        bg: "rgba(245,158,11,0.10)",
        glow: "none",
    },
    WATCH: {
        label: "WATCH",
        color: "var(--info)",
        bg: "rgba(6,182,212,0.08)",
        glow: "none",
    },
    NOISE: {
        label: "NOISE",
        color: "var(--text-dim)",
        bg: "rgba(148,163,184,0.06)",
        glow: "none",
    },
};

function tierFor(t: string) {
    return TIER_CONFIG[t] ?? TIER_CONFIG.NOISE;
}

// ─── Sub-components ───────────────────────────────────────────────────────────

function ScoreBar({ value, max, color }: { value: number; max: number; color: string }) {
    const pct = Math.min(100, (value / max) * 100);
    return (
        <div
            style={{
                height: 3,
                borderRadius: 2,
                background: "rgba(148,163,184,0.12)",
                overflow: "hidden",
                flex: 1,
            }}
        >
            <div
                style={{
                    height: "100%",
                    width: `${pct}%`,
                    background: color,
                    borderRadius: 2,
                    transition: "width 0.4s ease",
                }}
            />
        </div>
    );
}

function timeAgo(iso: string | null): string {
    if (!iso) return "";
    const t = new Date(iso.endsWith("Z") ? iso : `${iso}Z`).getTime();
    if (Number.isNaN(t)) return "";
    const s = Math.max(0, Math.floor((Date.now() - t) / 1000));
    if (s < 60) return `${s}s ago`;
    if (s < 3600) return `${Math.floor(s / 60)}m ago`;
    if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
    return `${Math.floor(s / 86400)}d ago`;
}

function CatalystCard({ signal }: { signal: CatalystSignalRow }) {
    const tier = tierFor(signal.priority_tier);
    const isCritical = signal.priority_tier === "CRITICAL";
    const baseSym = signal.symbol.replace("-USD", "");

    return (
        <div
            style={{
                background: tier.bg,
                border: `1px solid ${isCritical ? "rgba(244,63,94,0.3)" : "rgba(148,163,184,0.08)"}`,
                borderRadius: 6,
                padding: "0.75rem",
                boxShadow: tier.glow,
                position: "relative",
                overflow: "hidden",
            }}
        >
            {/* Critical pulse ring */}
            {isCritical && (
                <span
                    style={{
                        position: "absolute",
                        top: 10,
                        right: 10,
                        width: 8,
                        height: 8,
                        borderRadius: "50%",
                        background: "var(--neg)",
                        boxShadow: "0 0 0 0 rgba(244,63,94,0.6)",
                        animation: "catalyst-pulse 1.4s infinite",
                    }}
                />
            )}

            {/* Header row */}
            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.5rem" }}>
                <span
                    style={{
                        fontSize: "0.58rem",
                        fontWeight: 900,
                        letterSpacing: "0.06em",
                        color: tier.color,
                        background: isCritical ? "rgba(244,63,94,0.18)" : "rgba(148,163,184,0.1)",
                        padding: "0.1rem 0.4rem",
                        borderRadius: 4,
                        whiteSpace: "nowrap",
                    }}
                >
                    {tier.label}
                </span>
                <span
                    style={{
                        fontSize: "0.82rem",
                        fontWeight: 800,
                        color: "var(--text-main)",
                        letterSpacing: "0.02em",
                    }}
                >
                    {baseSym}
                </span>
                <span
                    className="mono"
                    style={{
                        marginLeft: "auto",
                        fontSize: "0.72rem",
                        fontWeight: 700,
                        color: tier.color,
                    }}
                >
                    {signal.catalyst_score.toFixed(1)}
                </span>
            </div>

            {/* Score component bars */}
            <div style={{ display: "flex", flexDirection: "column", gap: "0.3rem", marginBottom: "0.5rem" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "0.45rem" }}>
                    <TrendingUp size={10} color="var(--accent-amber)" style={{ flexShrink: 0 }} />
                    <span style={{ fontSize: "0.58rem", color: "var(--text-dim)", width: 52 }}>
                        Vol {signal.volume_surge_ratio.toFixed(2)}x
                    </span>
                    <ScoreBar value={signal.volume_surge_score} max={40} color="var(--accent-amber)" />
                </div>

                <div style={{ display: "flex", alignItems: "center", gap: "0.45rem" }}>
                    <Code2 size={10} color="var(--accent-cyan)" style={{ flexShrink: 0 }} />
                    <span style={{ fontSize: "0.58rem", color: "var(--text-dim)", width: 52 }}>
                        {signal.commit_count_4w} commits
                    </span>
                    <ScoreBar value={signal.dev_activity_score} max={30} color="var(--accent-cyan)" />
                </div>

                <div style={{ display: "flex", alignItems: "center", gap: "0.45rem" }}>
                    <Newspaper size={10} color="var(--accent-purple)" style={{ flexShrink: 0 }} />
                    <span style={{ fontSize: "0.58rem", color: "var(--text-dim)", width: 52 }}>News</span>
                    <ScoreBar value={signal.news_score} max={20} color="var(--accent-purple)" />
                </div>
            </div>

            {/* Keywords */}
            {signal.catalyst_keywords.length > 0 && (
                <div
                    style={{
                        display: "flex",
                        flexWrap: "wrap",
                        gap: "0.25rem",
                        marginBottom: signal.top_headline ? "0.4rem" : 0,
                    }}
                >
                    {signal.catalyst_keywords.slice(0, 4).map((kw) => (
                        <span
                            key={kw}
                            style={{
                                fontSize: "0.53rem",
                                fontWeight: 700,
                                letterSpacing: "0.04em",
                                color: "var(--accent-purple)",
                                background: "rgba(168,85,247,0.1)",
                                padding: "0.08rem 0.3rem",
                                borderRadius: 3,
                                textTransform: "uppercase",
                            }}
                        >
                            {kw}
                        </span>
                    ))}
                </div>
            )}

            {/* Top headline */}
            {signal.top_headline && (
                <p
                    style={{
                        fontSize: "0.62rem",
                        color: "var(--text-3)",
                        lineHeight: 1.4,
                        marginTop: "0.3rem",
                        overflow: "hidden",
                        display: "-webkit-box",
                        WebkitLineClamp: 2,
                        WebkitBoxOrient: "vertical" as React.CSSProperties["WebkitBoxOrient"],
                    }}
                >
                    {signal.top_headline}
                </p>
            )}

            {/* Footer */}
            <div
                className="mono"
                style={{
                    display: "flex",
                    justifyContent: "space-between",
                    marginTop: "0.4rem",
                    fontSize: "0.56rem",
                    color: "var(--text-dim)",
                }}
            >
                <span>
                    {signal.scorer_boost > 0
                        ? `+${signal.scorer_boost.toFixed(1)} pts boost`
                        : "no boost yet"}
                </span>
                <span>{timeAgo(signal.scraped_at)}</span>
            </div>
        </div>
    );
}

// ─── Main Component ───────────────────────────────────────────────────────────
const TIER_FILTERS = ["CRITICAL", "HIGH", "WATCH"] as const;
type TierFilter = (typeof TIER_FILTERS)[number];

export const CatalystFeed: React.FC = () => {
    const [signals, setSignals] = useState<CatalystSignalRow[]>([]);
    const [totalSignals, setTotalSignals] = useState(0);
    const [generatedAt, setGeneratedAt] = useState<string | null>(null);
    const [minTier, setMinTier] = useState<TierFilter>("HIGH");
    const [loading, setLoading] = useState(false);
    const [refreshing, setRefreshing] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const load = useCallback(async (tier = minTier) => {
        setLoading(true);
        setError(null);
        try {
            const data = await fetchCatalystFeed(tier);
            setSignals(data.signals);
            setTotalSignals(data.total_signals);
            setGeneratedAt(data.generated_at);
        } catch (e: any) {
            setError(e?.message ?? "Failed to load catalyst feed");
        } finally {
            setLoading(false);
        }
    }, [minTier]);

    useEffect(() => {
        load(minTier);
        const interval = setInterval(() => load(minTier), 60_000);
        return () => clearInterval(interval);
    }, [load, minTier]);

    const handleRefresh = async () => {
        setRefreshing(true);
        try {
            await triggerCatalystRefresh();
            // Wait a couple of seconds for the background task to at least start
            await new Promise((r) => setTimeout(r, 2500));
            await load(minTier);
        } catch {
            /* ignore */
        } finally {
            setRefreshing(false);
        }
    };

    const handleTierChange = (tier: TierFilter) => {
        setMinTier(tier);
        load(tier);
    };

    const criticalCount = signals.filter((s) => s.priority_tier === "CRITICAL").length;
    const highCount = signals.filter((s) => s.priority_tier === "HIGH").length;

    return (
        <>
            {/* Pulse animation keyframes */}
            <style>{`
                @keyframes catalyst-pulse {
                    0%   { box-shadow: 0 0 0 0 rgba(244,63,94,0.6); }
                    70%  { box-shadow: 0 0 0 6px rgba(244,63,94,0); }
                    100% { box-shadow: 0 0 0 0 rgba(244,63,94,0); }
                }
                @keyframes catalyst-spin {
                    from { transform: rotate(0deg); }
                    to   { transform: rotate(360deg); }
                }
            `}</style>

            <div style={{ background: "var(--surface-3)", overflow: "hidden" }}>
                {/* ── Header ── */}
                <div
                    style={{
                        background: "var(--surface-1)",
                        padding: "1rem 1.25rem",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "space-between",
                        borderBottom: "1px solid rgba(148,163,184,0.06)",
                    }}
                >
                    <div style={{ display: "flex", alignItems: "center", gap: "0.6rem" }}>
                        <Zap
                            size={14}
                            color={criticalCount > 0 ? "var(--neg)" : "var(--accent-amber)"}
                        />
                        <span
                            style={{
                                fontSize: "0.72rem",
                                fontWeight: 800,
                                letterSpacing: "0.06em",
                                color: "var(--text-main)",
                            }}
                        >
                            CATALYST FEED
                        </span>
                    </div>

                    <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                        {criticalCount > 0 && (
                            <span
                                className="mono"
                                style={{
                                    fontSize: "0.6rem",
                                    fontWeight: 800,
                                    padding: "0.15rem 0.5rem",
                                    borderRadius: 5,
                                    color: "var(--neg)",
                                    background: "rgba(244,63,94,0.14)",
                                    letterSpacing: "0.04em",
                                }}
                            >
                                {criticalCount} CRIT
                            </span>
                        )}
                        <span
                            className="mono"
                            style={{
                                fontSize: "0.6rem",
                                fontWeight: 700,
                                padding: "0.15rem 0.5rem",
                                borderRadius: 5,
                                color: "var(--text-dim)",
                                background: "rgba(148,163,184,0.1)",
                            }}
                        >
                            {totalSignals}
                        </span>
                        <button
                            type="button"
                            onClick={handleRefresh}
                            disabled={refreshing}
                            title="Trigger fresh catalyst scrape"
                            style={{
                                display: "flex",
                                alignItems: "center",
                                justifyContent: "center",
                                width: 24,
                                height: 24,
                                border: "none",
                                borderRadius: 5,
                                background: "rgba(6,182,212,0.1)",
                                color: "var(--accent-cyan)",
                                cursor: refreshing ? "wait" : "pointer",
                                opacity: refreshing ? 0.6 : 1,
                            }}
                        >
                            <RefreshCw
                                size={11}
                                style={
                                    refreshing
                                        ? { animation: "catalyst-spin 0.8s linear infinite" }
                                        : undefined
                                }
                            />
                        </button>
                    </div>
                </div>

                {/* ── Tier filter tabs ── */}
                <div
                    style={{
                        display: "flex",
                        gap: "0.25rem",
                        padding: "0.5rem 1.25rem",
                        background: "var(--surface-2)",
                        borderBottom: "1px solid rgba(148,163,184,0.06)",
                    }}
                >
                    {TIER_FILTERS.map((tier) => {
                        const cfg = tierFor(tier);
                        const active = minTier === tier;
                        return (
                            <button
                                key={tier}
                                type="button"
                                onClick={() => handleTierChange(tier)}
                                style={{
                                    fontSize: "0.58rem",
                                    fontWeight: 800,
                                    letterSpacing: "0.05em",
                                    padding: "0.2rem 0.6rem",
                                    borderRadius: 4,
                                    border: "none",
                                    cursor: "pointer",
                                    color: active ? cfg.color : "var(--text-dim)",
                                    background: active ? cfg.bg : "transparent",
                                    transition: "all 0.15s ease",
                                }}
                            >
                                {tier}
                            </button>
                        );
                    })}
                    <span
                        className="mono"
                        style={{
                            marginLeft: "auto",
                            fontSize: "0.55rem",
                            color: "var(--text-dim)",
                            alignSelf: "center",
                        }}
                    >
                        {generatedAt ? `as of ${timeAgo(generatedAt)}` : ""}
                    </span>
                </div>

                {/* ── Body ── */}
                <div style={{ padding: "0.75rem 1.25rem 1rem" }}>
                    {loading && signals.length === 0 ? (
                        <div
                            style={{
                                padding: "2rem 0",
                                textAlign: "center",
                                fontSize: "0.68rem",
                                color: "var(--text-dim)",
                                display: "flex",
                                alignItems: "center",
                                justifyContent: "center",
                                gap: "0.5rem",
                            }}
                        >
                            <Activity size={14} style={{ animation: "catalyst-spin 1s linear infinite" }} />
                            Scanning...
                        </div>
                    ) : error ? (
                        <div
                            style={{
                                padding: "1.5rem 0",
                                textAlign: "center",
                                fontSize: "0.68rem",
                                color: "var(--neg)",
                            }}
                        >
                            {error}
                        </div>
                    ) : signals.length === 0 ? (
                        <div
                            style={{
                                padding: "1.5rem 0",
                                textAlign: "center",
                                fontSize: "0.68rem",
                                color: "var(--text-dim)",
                            }}
                        >
                            No {minTier.toLowerCase()} signals right now.
                            <div style={{ marginTop: "0.35rem", fontSize: "0.6rem" }}>
                                The daemon runs every 15 minutes — click ↺ to refresh.
                            </div>
                        </div>
                    ) : (
                        <div style={{ display: "flex", flexDirection: "column", gap: "0.6rem" }}>
                            {signals.map((sig) => (
                                <CatalystCard key={sig.symbol} signal={sig} />
                            ))}
                        </div>
                    )}
                </div>
            </div>
        </>
    );
};

export default CatalystFeed;
