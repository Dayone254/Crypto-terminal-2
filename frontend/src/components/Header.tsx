"use client";

import React, { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { Layout, Volume2, User } from "lucide-react";
import { apiFetch } from "@/lib/api";
import { useSidebar } from "@/contexts/SidebarContext";

interface HeaderProps {
    universeCount?: number;
    activeCount?: number;
    highConvictionCount?: number;
    selectedFilter?: string;
    onSelectFilter?: (filter: string) => void;
}

interface MacroMetrics {
    btcDominance: number | null;
    ethBtc: number | null;
    fundingAvg: number | null;
    wsLatencyMs: number | null;
}

async function measureLatency(): Promise<number> {
    const t0 = Date.now();
    try {
        await apiFetch("/api/v1/scan/status");
        return Date.now() - t0;
    } catch {
        return -1;
    }
}

async function fetchSafeJson(url: string) {
    try {
        const res = await fetch(url, { cache: "no-store" });
        if (!res.ok) return null;
        return await res.json();
    } catch {
        return null;
    }
}

export const Header: React.FC<HeaderProps> = ({
    universeCount = 512,
    activeCount = 0,
    highConvictionCount = 0,
    selectedFilter = "ALL",
    onSelectFilter,
}) => {
    const { toggleSidebar } = useSidebar();
    const [metrics, setMetrics] = useState<MacroMetrics>({
        btcDominance: null,
        ethBtc: null,
        fundingAvg: null,
        wsLatencyMs: null,
    });

    const loadMetrics = useCallback(async () => {
        // Route CoinGecko calls through Next.js server-side proxy to avoid CORS blocks.
        const [cgGlobal, cgPrices, latencyMs, marketsRes] = await Promise.allSettled([
            fetchSafeJson("/api/coingecko/global"),
            fetchSafeJson("/api/coingecko/price?ids=ethereum&vs_currencies=btc"),
            measureLatency(),
            apiFetch("/api/v1/markets").then((r) => (r.ok ? r.json() : null)),
        ]);

        let btcDominance: number | null = null;
        let ethBtc: number | null = null;
        if (cgGlobal.status === "fulfilled" && cgGlobal.value?.data?.market_cap_percentage?.btc) {
            btcDominance = cgGlobal.value.data.market_cap_percentage.btc;
        }
        if (cgPrices.status === "fulfilled" && cgPrices.value?.ethereum?.btc) {
            ethBtc = cgPrices.value.ethereum.btc;
        }

        let fundingAvg: number | null = null;
        if (marketsRes.status === "fulfilled" && Array.isArray(marketsRes.value)) {
            const markets = marketsRes.value;
            // Fallback ETH/BTC calculation from market spot prices if CoinGecko is rate-limited
            if (ethBtc === null) {
                const eth = markets.find((m: any) => m.product_id === "ETH-USD");
                const btc = markets.find((m: any) => m.product_id === "BTC-USD");
                if (eth?.last_price && btc?.last_price && btc.last_price > 0) {
                    ethBtc = eth.last_price / btc.last_price;
                }
            }

            const withFunding = markets.filter(
                (m: any) => typeof m.funding_rate === "number"
            );
            if (withFunding.length > 0) {
                fundingAvg =
                    withFunding.reduce((sum: number, m: any) => sum + m.funding_rate, 0) /
                    withFunding.length;
            }
        }

        const latency = latencyMs.status === "fulfilled" ? latencyMs.value : null;

        setMetrics((prev) => ({
            btcDominance: btcDominance ?? prev.btcDominance,
            ethBtc: ethBtc ?? prev.ethBtc,
            fundingAvg,
            wsLatencyMs: latency,
        }));
    }, []);

    useEffect(() => {
        loadMetrics();
        const interval = setInterval(loadMetrics, 30000);
        return () => clearInterval(interval);
    }, [loadMetrics]);

    const quickFilters = [
        { label: "All Setups", key: "ALL" },
        { label: "Breakout Zone", key: "ENTRY_ZONE" },
        { label: "Coiled Vol Squeeze", key: "COILED" },
        { label: "High CVD Inflow", key: "EARLY" },
        { label: "Institutional Watchlist", key: "WATCHLIST" },
    ];

    const fmtPct = (v: number | null, decimals = 1) =>
        v === null ? "—" : `${v.toFixed(decimals)}%`;

    const fmtFunding = (v: number | null) => {
        if (v === null) return "—";
        const sign = v >= 0 ? "+" : "";
        return `${sign}${(v * 100).toFixed(4)}%/8h`;
    };

    const latencyLabel = () => {
        if (metrics.wsLatencyMs === null) return "—";
        if (metrics.wsLatencyMs < 0) return "TIMEOUT";
        return `${metrics.wsLatencyMs}ms`;
    };

    const latencyColor = () => {
        if (metrics.wsLatencyMs === null || metrics.wsLatencyMs < 0) return "var(--outline)";
        if (metrics.wsLatencyMs < 100) return "var(--primary-fixed-dim)";
        if (metrics.wsLatencyMs < 500) return "var(--warn)";
        return "var(--secondary)";
    };

    const macroTiles = [
        { label: "BTC.D", value: fmtPct(metrics.btcDominance), color: "var(--primary-fixed-dim)" },
        { label: "ETH/BTC", value: metrics.ethBtc === null ? "—" : metrics.ethBtc.toFixed(4), color: "var(--secondary)" },
        { label: "FUNDING AVG", value: fmtFunding(metrics.fundingAvg), color: metrics.fundingAvg !== null && metrics.fundingAvg >= 0 ? "var(--primary-fixed-dim)" : "var(--secondary)" },
    ];

    return (
        <header
            style={{
                position: "fixed",
                top: 0,
                left: "var(--sidebar-width, 256px)",
                right: 0,
                height: "112px",
                backgroundColor: "var(--surface-container-low)",
                borderBottom: "1px solid var(--outline-variant)",
                display: "flex",
                flexDirection: "column",
                zIndex: 40,
                transition: "var(--sidebar-transition, all 0.3s)",
                justifyContent: "space-between",
                boxShadow: "0 1px 8px rgba(0,0,0,0.3)",
            }}
        >
            {/* ── Tier 1: Macro Metrics Ribbon ── */}
            <div
                style={{
                    height: "56px",
                    padding: "0 1rem",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    gap: "1rem",
                    borderBottom: "1px solid var(--outline-variant)",
                }}
            >
                {/* Left: Live market tiles */}
                <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", overflowX: "auto" }}>
                    {macroTiles.map((tile) => (
                        <div
                            key={tile.label}
                            className="font-mono-data-compact"
                            style={{
                                display: "flex",
                                alignItems: "center",
                                gap: "0.25rem",
                                padding: "0.25rem 0.5rem",
                                borderRadius: "4px",
                                backgroundColor: "var(--surface-container)",
                            }}
                        >
                            <span style={{ color: "var(--on-surface-variant)" }}>{tile.label}</span>
                            <span style={{ color: tile.color, fontWeight: 700 }}>
                                {tile.value}
                            </span>
                        </div>
                    ))}

                    {/* WS Latency — measured via real ping */}
                    <div
                        className="font-mono-data-compact"
                        style={{
                            display: "flex",
                            alignItems: "center",
                            gap: "0.25rem",
                            padding: "0.25rem 0.5rem",
                            borderRadius: "4px",
                            backgroundColor: "var(--surface-container-lowest)",
                        }}
                    >
                        <span
                            style={{
                                width: "6px",
                                height: "6px",
                                borderRadius: "50%",
                                backgroundColor: latencyColor(),
                            }}
                        />
                        <span style={{ color: "var(--on-surface-variant)" }}>API LATENCY</span>
                        <span style={{ color: latencyColor(), fontWeight: 700 }}>{latencyLabel()}</span>
                    </div>
                </div>

                {/* Right: Universe count HUD + icon buttons */}
                <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
                    <div
                        style={{
                            display: "flex",
                            alignItems: "center",
                            gap: "0.5rem",
                            padding: "0.25rem 0.65rem",
                            backgroundColor: "var(--surface-container)",
                            borderRadius: "6px",
                        }}
                    >
                        <div className="font-mono-data-compact" style={{ display: "flex", gap: "0.25rem" }}>
                            <span style={{ color: "var(--on-surface-variant)" }}>UNIVERSE:</span>
                            <span style={{ color: "var(--on-surface)", fontWeight: 700 }}>{universeCount}</span>
                        </div>
                        <span style={{ color: "var(--outline-variant)" }}>|</span>
                        <div className="font-mono-data-compact" style={{ display: "flex", gap: "0.25rem" }}>
                            <span style={{ color: "var(--on-surface-variant)" }}>ACTIVE:</span>
                            <span style={{ color: "var(--primary-fixed-dim)", fontWeight: 700 }}>{activeCount}</span>
                        </div>
                        <span style={{ color: "var(--outline-variant)" }}>|</span>
                        <div className="font-mono-data-compact" style={{ display: "flex", gap: "0.25rem" }}>
                            <span style={{ color: "var(--on-surface-variant)" }}>HIGH CONVICTION:</span>
                            <span style={{ color: "var(--secondary)", fontWeight: 700 }}>{highConvictionCount}</span>
                        </div>
                    </div>

                    <div style={{ display: "flex", alignItems: "center", gap: "0.25rem" }}>
                        <button
                            onClick={toggleSidebar}
                            style={{
                                width: "32px", height: "32px", borderRadius: "4px",
                                backgroundColor: "var(--surface-container)", border: "none",
                                display: "flex", alignItems: "center", justifyContent: "center",
                                color: "var(--on-surface-variant)", cursor: "pointer",
                            }}
                            title="Toggle Sidebar"
                        >
                            <Layout size={16} />
                        </button>
                        <Link
                            href="/profile"
                            style={{
                                width: "32px", height: "32px", borderRadius: "4px",
                                backgroundColor: "var(--surface-container)", border: "none",
                                display: "flex", alignItems: "center", justifyContent: "center",
                                color: "var(--on-surface-variant)", cursor: "pointer",
                                textDecoration: "none"
                            }}
                            title="Sound Alerts & Audio Engine"
                        >
                            <Volume2 size={16} />
                        </Link>
                        <Link
                            href="/profile"
                            style={{
                                width: "32px", height: "32px", borderRadius: "50%",
                                backgroundColor: "var(--primary)",
                                display: "flex", alignItems: "center", justifyContent: "center",
                                color: "var(--on-primary-fixed)",
                                textDecoration: "none"
                            }}
                            title="User Profile & Settings"
                        >
                            <User size={16} />
                        </Link>
                    </div>
                </div>
            </div>

            {/* ── Tier 2: Quick Filters ── */}
            <div
                style={{
                    height: "56px",
                    padding: "0 1rem",
                    display: "flex",
                    alignItems: "center",
                    backgroundColor: "rgba(10, 14, 21, 0.8)",
                }}
            >

                <div style={{ display: "flex", alignItems: "center", gap: "0.35rem", overflowX: "auto" }}>
                    <span className="font-label-caps" style={{ color: "var(--outline)", marginRight: "0.25rem" }}>
                        Quick Filters:
                    </span>
                    {quickFilters.map((q) => {
                        const isSelected = selectedFilter === q.key;
                        return (
                            <button
                                key={q.key}
                                onClick={() => onSelectFilter?.(q.key)}
                                className="font-mono-data-compact"
                                style={{
                                    padding: "0.25rem 0.5rem",
                                    borderRadius: "4px",
                                    border: "none",
                                    cursor: "pointer",
                                    backgroundColor: isSelected ? "var(--surface-container-high)" : "var(--surface-container)",
                                    color: isSelected ? "var(--primary-fixed-dim)" : "var(--on-surface-variant)",
                                    fontWeight: isSelected ? 700 : 500,
                                }}
                            >
                                {q.label}
                            </button>
                        );
                    })}
                </div>
            </div>
        </header>
    );
};
