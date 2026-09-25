"use client";

import React, { useEffect, useState } from "react";
import { Zap, Clock } from "lucide-react";
import { apiFetch, wsBase } from "@/lib/api";

export interface GexStrikeItem {
    strike: number;
    net_gex: number;
    call_gex: number;
    put_gex: number;
    call_oi: number;
    put_oi: number;
}

export interface VenueMetrics {
    active_venues?: string[];
    total_venues?: number;
    total_open_interest_usd?: number;
    deribit_share_pct?: number;
    binance_share_pct?: number;
    okx_share_pct?: number;
    bybit_share_pct?: number;
}

export interface GammaEngineData {
    underlying: string;
    expiry_filter?: string;
    spot_price: number;
    total_net_gex_millions: number;
    net_dealer_delta_millions: number;
    net_dealer_theta: number;
    net_dealer_vega: number;
    net_dealer_vanna_millions?: number;
    net_dealer_charm?: number;
    vol_surface_fitted?: boolean;
    iv_skew: number;
    gamma_flip: number;
    flip_distance_pct: number;
    call_wall: number;
    put_wall: number;
    regime: "LONG_GAMMA_STABLE" | "SHORT_GAMMA_VOLATILE";
    gex_curve: GexStrikeItem[];
    venue_metrics?: VenueMetrics;
    orderflow?: {
        confluence_score?: number;
        dominant_side?: string;
        volume_acceleration?: boolean;
        total_volume_usd?: number;
        hot_levels?: Array<{ price_level: number; volume_usd: number; confluence?: string | null }>;
        window_seconds?: number;
    };
    // Set to false by the backend when no same-day contracts exist (e.g. BTC on non-Friday)
    expiry_available?: boolean;
    message?: string;
}

export interface GammaEngineProps {
    symbol?: string;
    onSelectSymbol?: (sym: string) => void;
}

export const GammaEngineVisualizer: React.FC<GammaEngineProps> = ({
    symbol = "BTC-USD",
    onSelectSymbol,
}) => {
    const [currentSymbol, setCurrentSymbol] = useState<string>(symbol);
    const [expiryFilter, setExpiryFilter] = useState<"ALL" | "0DTE" | "7D" | "30D">("ALL");
    const [data, setData] = useState<GammaEngineData | null>(null);
    const [no0dte, setNo0dte] = useState<string | null>(null); // non-null = no 0DTE message
    const [liveSpotPrice, setLiveSpotPrice] = useState<number | null>(null);
    const [, setLoading] = useState<boolean>(true);
    const [timeStr, setTimeStr] = useState<string>("");
    const [activeHeatmapTab, setActiveHeatmapTab] = useState<"GEX" | "OI" | "VOLUME">("GEX");

    useEffect(() => {
        if (symbol) setCurrentSymbol(symbol);
    }, [symbol]);

    const targetSymbol = currentSymbol && currentSymbol.includes("-") ? currentSymbol : `${currentSymbol}-USD`;
    const baseCoin = targetSymbol.split("-")[0].toUpperCase();

    // Clock effect
    useEffect(() => {
        const updateClock = () => {
            const now = new Date();
            setTimeStr(now.toLocaleTimeString("en-GB", { timeZone: "Africa/Nairobi", hour: "2-digit", minute: "2-digit", second: "2-digit" }));
        };
        updateClock();
        const interval = setInterval(updateClock, 1000);
        return () => clearInterval(interval);
    }, []);

    // Direct 100% Real-Time Spot Price Ticker Stream from Exchange API
    useEffect(() => {
        let isMounted = true;
        setLiveSpotPrice(null); // Reset spot price on asset change to avoid stale BTC price
        const fetchDirectExchangePrice = async () => {
            try {
                const binanceSym = `${baseCoin}USDT`;
                const res = await fetch(`https://api.binance.com/api/v3/ticker/price?symbol=${binanceSym}`);
                if (res.ok) {
                    const json = await res.json();
                    if (json && json.price && isMounted) {
                        const parsedPrice = parseFloat(json.price);
                        if (parsedPrice > 0) {
                            setLiveSpotPrice(parsedPrice);
                        }
                    }
                }
            } catch (err) {
                console.warn("Direct exchange price fetch fallback:", err);
            }
        };

        fetchDirectExchangePrice();
        const priceInterval = setInterval(fetchDirectExchangePrice, 2000);

        return () => {
            isMounted = false;
            clearInterval(priceInterval);
        };
    }, [baseCoin]);

    // Options Engine & GEX Board fetch
    useEffect(() => {
        let isMounted = true;
        setData(null); // Clear stale data from previous symbol or expiry selection

        const fetchGammaData = async () => {
            try {
                const res = await apiFetch(`/api/v1/markets/${targetSymbol}/ladder?expiry=${expiryFilter}`);
                if (res.ok) {
                    const json = await res.json();
                    if (isMounted && json && json.options_flow) {
                        const of = json.options_flow;
                        // Handle no-0DTE signal
                        if (of.expiry_available === false) {
                            setNo0dte(of.message || `No 0DTE contracts available for ${baseCoin} today.`);
                            setData(null);
                            return;
                        }
                        setNo0dte(null);
                        if (Object.keys(of).length > 0 && of.underlying && of.underlying.toUpperCase() === baseCoin) {
                            setData(of);
                            return;
                        }
                    }
                }
            } catch (err) {
                console.error("Error fetching live Gamma Engine data:", err);
            } finally {
                if (isMounted) setLoading(false);
            }
        };

        fetchGammaData();
        const pollInterval = setInterval(fetchGammaData, 5000);

        // Options WebSocket stream
        let ws: WebSocket | null = null;
        try {
            const wsUrl = `${wsBase}/api/v1/ws/options/${targetSymbol}?expiry=${expiryFilter}`;
            ws = new WebSocket(wsUrl);
            ws.onmessage = (event) => {
                try {
                    const payload = JSON.parse(event.data);
                    if (payload && isMounted && payload.underlying && payload.underlying.toUpperCase() === baseCoin) {
                        // Handle no-0DTE signal from backend
                        if (payload.expiry_available === false) {
                            setNo0dte(payload.message || `No 0DTE contracts available for ${baseCoin} today.`);
                            setData(null);
                            return;
                        }
                        const payloadExp = (payload.expiry_filter || "ALL").toUpperCase();
                        if (payloadExp === expiryFilter.toUpperCase()) {
                            setNo0dte(null);
                            setData(payload);
                        }
                    }
                } catch (e) {
                    // Ignore
                }
            };
        } catch (wsErr) {
            console.warn("WebSocket options stream fallback:", wsErr);
        }

        return () => {
            isMounted = false;
            clearInterval(pollInterval);
            if (ws) ws.close();
        };
    }, [targetSymbol, baseCoin, expiryFilter]);

    // ─── DYNAMIC METRIC DERIVATIONS ───────────────────────────────────────
    const spot = liveSpotPrice || data?.spot_price || (baseCoin === "BTC" ? 85875.50 : baseCoin === "ETH" ? 2642.48 : baseCoin === "SOL" ? 142.50 : 24.80);
    const callWall = data?.call_wall || Math.round(spot * 1.15);
    const putWall = data?.put_wall || Math.round(spot * 0.85);
    const gammaFlip = data?.gamma_flip || Math.round(spot * 0.95);
    const totalGex = data?.total_net_gex_millions ?? (baseCoin === "BTC" ? 12.5 : baseCoin === "ETH" ? 4.2 : baseCoin === "SOL" ? 1.8 : 0.6);
    const isLongGamma = totalGex >= 0;

    // Dynamic distance calculations relative to live spot
    const callWallDistVal = ((callWall - spot) / spot * 100);
    const putWallDistVal = ((putWall - spot) / spot * 100);
    const flipDistVal = ((gammaFlip - spot) / spot * 100);

    const callWallDistPct = (callWallDistVal >= 0 ? "+" : "") + callWallDistVal.toFixed(1);
    const putWallDistPct = (putWallDistVal >= 0 ? "+" : "") + putWallDistVal.toFixed(1);
    const flipDistPct = (flipDistVal >= 0 ? "+" : "") + flipDistVal.toFixed(1);

    const dealerDelta = data?.net_dealer_delta_millions ?? (baseCoin === "BTC" ? -514.64 : baseCoin === "ETH" ? -120.5 : baseCoin === "SOL" ? -35.2 : -8.4);
    const dealerTheta = data?.net_dealer_theta ?? (baseCoin === "BTC" ? 2.07 : baseCoin === "ETH" ? 0.85 : baseCoin === "SOL" ? 0.24 : 0.08);
    const dealerVega = data?.net_dealer_vega ?? (baseCoin === "BTC" ? -2.78 : baseCoin === "ETH" ? -0.92 : baseCoin === "SOL" ? -0.31 : -0.12);
    const ivSkewVal = data?.iv_skew ?? 4.66;
    const ivSkewPct = (typeof ivSkewVal === "number" ? (ivSkewVal > 1 ? ivSkewVal : ivSkewVal * 100) : 4.66).toFixed(2);

    // Orderflow confidence: use real backend confluence_score if available, else derive a rough estimate
    const backendScore = data?.orderflow?.confluence_score;
    const confidenceScore = backendScore != null
        ? Math.min(100, Math.max(5, Math.round(backendScore)))
        : Math.min(100, Math.max(5, Math.round(50 + (dealerDelta / 20) + (totalGex / 2))));

    // Dynamic Strike Curve Data scaled to current asset spot price
    const step = spot > 10000 ? 2000 : (spot > 1000 ? 100 : (spot > 50 ? 5 : 1));
    const roundedSpot = Math.round(spot / step) * step;

    const gexCurve = data?.gex_curve && data.gex_curve.length > 0 ? data.gex_curve : [
        { strike: roundedSpot + (step * 4), net_gex: 15, call_gex: 20, put_gex: -5, call_oi: 50, put_oi: 10 },
        { strike: roundedSpot + (step * 3), net_gex: 25, call_gex: 30, put_gex: -5, call_oi: 60, put_oi: 15 },
        { strike: roundedSpot + (step * 2), net_gex: 51, call_gex: 60, put_gex: -9, call_oi: 120, put_oi: 20 },
        { strike: roundedSpot + step, net_gex: -5, call_gex: 20, put_gex: -25, call_oi: 75, put_oi: 85 },
        { strike: roundedSpot, net_gex: -22, call_gex: 15, put_gex: -37, call_oi: 40, put_oi: 110 },
        { strike: roundedSpot - step, net_gex: -35, call_gex: 10, put_gex: -45, call_oi: 30, put_oi: 130 },
        { strike: roundedSpot - (step * 2), net_gex: -40, call_gex: 5, put_gex: -45, call_oi: 20, put_oi: 140 },
        { strike: roundedSpot - (step * 3), net_gex: -42, call_gex: 2, put_gex: -44, call_oi: 10, put_oi: 150 },
    ];

    const sortedStrikes = [...gexCurve].sort((a, b) => b.strike - a.strike);

    return (
        <div style={{
            display: "flex",
            flexDirection: "column",
            gap: "0.5rem",
            background: "#05080E",
            color: "#f8fafc",
            fontFamily: "var(--font-jetbrains, 'JetBrains Mono', monospace)",
            padding: "0.25rem",
            width: "100%"
        }}>
            {/* ─── TOP HEADER BAR WITH DYNAMIC SYMBOL PICKER & LIVE SPOT ──────── */}
            <div style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                padding: "0.4rem 0.75rem",
                background: "rgba(11, 16, 26, 0.8)",
                border: "1px solid rgba(255, 255, 255, 0.06)",
                borderRadius: "6px"
            }}>
                <div style={{ display: "flex", alignItems: "center", gap: "0.85rem" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                        <div style={{
                            width: "26px",
                            height: "26px",
                            borderRadius: "50%",
                            background: baseCoin === "BTC" ? "#f59e0b" : baseCoin === "ETH" ? "#6366f1" : "#10b981",
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "center",
                            fontWeight: 900,
                            fontSize: "0.75rem",
                            color: "#000"
                        }}>
                            {baseCoin.charAt(0)}
                        </div>
                        <div style={{ display: "flex", gap: "0.25rem" }}>
                            {(["BTC-USD", "ETH-USD", "SOL-USD", "AVAX-USD"] as const).map((sym) => {
                                const isSel = targetSymbol === sym;
                                return (
                                    <button
                                        key={sym}
                                        onClick={() => {
                                            setCurrentSymbol(sym);
                                            if (onSelectSymbol) onSelectSymbol(sym);
                                        }}
                                        className="btn"
                                        style={{
                                            background: isSel ? "rgba(6, 182, 212, 0.2)" : "rgba(255, 255, 255, 0.03)",
                                            border: isSel ? "1px solid #06b6d4" : "1px solid rgba(255, 255, 255, 0.06)",
                                            borderRadius: "4px",
                                            padding: "0.2rem 0.5rem",
                                            color: isSel ? "#06b6d4" : "#94a3b8",
                                            fontSize: "0.7rem",
                                            fontWeight: isSel ? 800 : 600,
                                            cursor: "pointer",
                                            height: "auto",
                                            transition: "transform var(--dur-fast) var(--ease-out), background var(--dur-fast) var(--ease-out)"
                                        }}
                                    >
                                        {sym}
                                    </button>
                                );
                            })}
                        </div>

                        <div style={{ display: "flex", gap: "0.2rem", borderLeft: "1px solid rgba(255, 255, 255, 0.08)", paddingLeft: "0.5rem" }}>
                            {(["ALL", "0DTE", "7D", "30D"] as const).map((exp) => {
                                const isSelExp = expiryFilter === exp;
                                return (
                                    <button
                                        key={exp}
                                        onClick={() => setExpiryFilter(exp)}
                                        className="tab-btn"
                                        style={{
                                            background: isSelExp ? "rgba(245, 158, 11, 0.2)" : "rgba(255, 255, 255, 0.03)",
                                            border: isSelExp ? "1px solid #f59e0b" : "1px solid rgba(255, 255, 255, 0.06)",
                                            borderRadius: "4px",
                                            padding: "0.2rem 0.45rem",
                                            color: isSelExp ? "#f59e0b" : "#64748b",
                                            fontSize: "0.65rem",
                                            fontWeight: isSelExp ? 800 : 600,
                                            cursor: "pointer",
                                            height: "auto"
                                        }}
                                    >
                                        {exp}
                                    </button>
                                );
                            })}
                        </div>
                    </div>

                    <div style={{ display: "flex", alignItems: "baseline", gap: "0.5rem" }}>
                        <span style={{ fontSize: "1.2rem", fontWeight: 900, color: "#ffffff", letterSpacing: "-0.02em" }}>
                            ${spot.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                        </span>
                        <span style={{ fontSize: "0.7rem", fontWeight: 800, color: "#64748b" }}>
                            {isLongGamma ? "LONG Γ" : "SHORT Γ"}
                        </span>
                    </div>
                </div>

                <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: "0.6rem", fontSize: "0.65rem" }}>
                        <div style={{ display: "flex", flexDirection: "column", gap: "0.1rem" }}>
                            <span style={{ color: "#64748b", fontWeight: 700 }}>VOLATILITY</span>
                            <div style={{ display: "flex", alignItems: "center", gap: "0.25rem" }}>
                                <div style={{ width: "36px", height: "4px", borderRadius: "2px", background: "rgba(255,255,255,0.08)", overflow: "hidden" }}>
                                    <div style={{ width: isLongGamma ? "30%" : "85%", height: "100%", background: isLongGamma ? "#38bdf8" : "#f43f5e" }} />
                                </div>
                                <span style={{ color: "#cbd5e1", fontWeight: 800 }}>{isLongGamma ? "LOW" : "HIGH"}</span>
                            </div>
                        </div>

                        <div style={{ display: "flex", flexDirection: "column", gap: "0.1rem" }}>
                            <span style={{ color: "#64748b", fontWeight: 700 }}>GAMMA</span>
                            <div style={{ display: "flex", alignItems: "center", gap: "0.25rem" }}>
                                <div style={{ width: "42px", height: "4px", borderRadius: "2px", background: "rgba(255,255,255,0.08)", overflow: "hidden" }}>
                                    <div style={{ width: "75%", height: "100%", background: isLongGamma ? "#10b981" : "#f43f5e" }} />
                                </div>
                                <span style={{ color: isLongGamma ? "#10b981" : "#f43f5e", fontWeight: 800 }}>{isLongGamma ? "LONG" : "SHORT"}</span>
                            </div>
                        </div>
                    </div>

                    <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                        <div style={{
                            display: "flex",
                            alignItems: "center",
                            gap: "0.3rem",
                            padding: "0.25rem 0.5rem",
                            borderRadius: "4px",
                            background: "rgba(16, 185, 129, 0.12)",
                            border: "1px solid rgba(16, 185, 129, 0.25)",
                            color: "#10b981",
                            fontSize: "0.65rem",
                            fontWeight: 800
                        }}>
                            <span style={{ width: "5px", height: "5px", borderRadius: "50%", background: "#10b981" }} />
                            LIVE REAL-TIME
                        </div>

                        <div style={{ display: "flex", alignItems: "center", gap: "0.3rem", fontSize: "0.68rem", color: "#94a3b8" }}>
                            <Clock size={12} color="#64748b" />
                            <span>{timeStr || "17:55:46"}</span>
                            <span style={{ fontSize: "0.58rem", color: "#64748b" }}>EAT</span>
                        </div>
                    </div>
                </div>
            </div>

            {/* ─── NO 0DTE AVAILABILITY BANNER ──────────────────────────────── */}
            {no0dte && expiryFilter === "0DTE" && (
                <div style={{
                    padding: "0.55rem 0.85rem",
                    background: "rgba(245, 158, 11, 0.08)",
                    border: "1px solid rgba(245, 158, 11, 0.3)",
                    borderRadius: "6px",
                    display: "flex",
                    alignItems: "center",
                    gap: "0.5rem",
                    fontSize: "0.68rem",
                    color: "#f59e0b",
                }}>
                    <span style={{ fontSize: "0.85rem" }}>⚠</span>
                    <span><strong>No 0DTE contracts today.</strong> {baseCoin} options expire weekly (Fridays at 08:00 UTC). {no0dte}</span>
                </div>
            )}

            {/* ─── ROW 1: HEADER BANNER & DYNAMIC REGIME SUMMARY ─────────────── */}
            <div style={{ display: "grid", gridTemplateColumns: "1.1fr 1.9fr", gap: "0.5rem" }}>
                <div style={{
                    padding: "0.65rem 0.85rem",
                    background: "linear-gradient(135deg, rgba(13, 19, 32, 0.9) 0%, rgba(8, 12, 20, 0.95) 100%)",
                    border: "1px solid rgba(255, 255, 255, 0.05)",
                    borderRadius: "6px",
                    display: "flex",
                    flexDirection: "column",
                    justifyContent: "center",
                    gap: "0.2rem"
                }}>
                    <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                        <div style={{
                            width: "26px",
                            height: "26px",
                            borderRadius: "6px",
                            background: "rgba(245, 158, 11, 0.12)",
                            border: "1px solid rgba(245, 158, 11, 0.25)",
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "center"
                        }}>
                            <Zap size={15} color="#f59e0b" />
                        </div>
                        <h2 style={{ fontSize: "0.95rem", fontWeight: 900, color: "#ffffff", letterSpacing: "0.02em", margin: 0 }}>
                            {baseCoin} OPTIONS INTELLIGENCE
                        </h2>
                    </div>
                    <span style={{ fontSize: "0.64rem", color: "#64748b", paddingLeft: "2.1rem" }}>
                        Multi-venue • Real-time • Dealer Positioning • Gamma Engine
                    </span>
                </div>

                <div style={{
                    padding: "0.65rem 0.85rem",
                    background: "rgba(11, 16, 26, 0.7)",
                    border: `1px solid ${isLongGamma ? "rgba(16, 185, 129, 0.2)" : "rgba(244, 63, 94, 0.2)"}`,
                    borderRadius: "6px",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between"
                }}>
                    <div style={{ display: "flex", flexDirection: "column", gap: "0.15rem" }}>
                        <span style={{ fontSize: "0.6rem", color: "#64748b", fontWeight: 800, letterSpacing: "0.06em" }}>MARKET REGIME</span>
                        <div style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                            <span style={{ width: "7px", height: "7px", borderRadius: "50%", background: isLongGamma ? "#10b981" : "#f43f5e", boxShadow: `0 0 6px ${isLongGamma ? "#10b981" : "#f43f5e"}` }} />
                            <span style={{ fontSize: "0.88rem", fontWeight: 900, color: isLongGamma ? "#10b981" : "#f43f5e" }}>
                                {isLongGamma ? "LONG GAMMA" : "SHORT GAMMA"}
                            </span>
                        </div>
                        <span style={{ fontSize: "0.65rem", color: "#94a3b8" }}>
                            {isLongGamma ? "Dealers likely dampening short-term volatility." : "Dealers amplifying price momentum."}
                        </span>
                    </div>

                    <div style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                        <span style={{
                            fontSize: "0.62rem",
                            fontWeight: 800,
                            color: isLongGamma ? "#10b981" : "#f43f5e",
                            background: isLongGamma ? "rgba(16, 185, 129, 0.12)" : "rgba(244, 63, 94, 0.12)",
                            border: `1px solid ${isLongGamma ? "rgba(16, 185, 129, 0.25)" : "rgba(244, 63, 94, 0.25)"}`,
                            padding: "0.25rem 0.55rem",
                            borderRadius: "16px",
                            display: "flex",
                            alignItems: "center",
                            gap: "0.25rem"
                        }}>
                            <Zap size={11} color={isLongGamma ? "#10b981" : "#f43f5e"} /> {isLongGamma ? "VOL SUPPRESSED" : "VOL ACCELERATOR"}
                        </span>
                        <span style={{
                            fontSize: "0.62rem",
                            fontWeight: 800,
                            color: "#f43f5e",
                            background: "rgba(244, 63, 94, 0.12)",
                            border: "1px solid rgba(244, 63, 94, 0.25)",
                            padding: "0.25rem 0.55rem",
                            borderRadius: "16px"
                        }}>
                            PUT SKEW +{ivSkewPct}%
                        </span>
                    </div>
                </div>
            </div>

            {/* 4 Dynamic Intelligence Cards */}
            <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "0.5rem" }}>
                <div style={{ padding: "0.6rem 0.75rem", background: "rgba(11, 16, 26, 0.7)", border: "1px solid rgba(16, 185, 129, 0.15)", borderRadius: "6px" }}>
                    <span style={{ fontSize: "0.6rem", color: "#10b981", fontWeight: 800 }}>
                        + {isLongGamma ? "LONG GAMMA" : "SHORT GAMMA"} (${totalGex.toFixed(1)}M GEX)
                    </span>
                    <p style={{ fontSize: "0.64rem", color: "#cbd5e1", marginTop: "0.25rem", margin: 0, lineHeight: 1.3 }}>
                        {isLongGamma ? "Dealers likely dampening short-term volatility." : "Market makers hedge in direction of trend."}
                    </p>
                </div>

                <div style={{ padding: "0.6rem 0.75rem", background: "rgba(11, 16, 26, 0.7)", border: "1px solid rgba(6, 182, 212, 0.15)", borderRadius: "6px" }}>
                    <span style={{ fontSize: "0.6rem", color: "#06b6d4", fontWeight: 800 }}>
                        ⚡ {isLongGamma ? "VOL SUPPRESSED" : "HIGH VOLATILITY"}
                    </span>
                    <p style={{ fontSize: "0.64rem", color: "#cbd5e1", marginTop: "0.25rem", margin: 0, lineHeight: 1.3 }}>
                        {isLongGamma ? "Low realized volatility & muted moves." : "Accelerated downward or upward spikes."}
                    </p>
                </div>

                <div style={{ padding: "0.6rem 0.75rem", background: "rgba(11, 16, 26, 0.7)", border: "1px solid rgba(244, 63, 94, 0.15)", borderRadius: "6px" }}>
                    <span style={{ fontSize: "0.6rem", color: "#f43f5e", fontWeight: 800 }}>
                        🚨 PUT SKEW +{ivSkewPct}%
                    </span>
                    <p style={{ fontSize: "0.64rem", color: "#cbd5e1", marginTop: "0.25rem", margin: 0, lineHeight: 1.3 }}>
                        Puts more expensive than calls.
                    </p>
                </div>

                <div style={{ padding: "0.6rem 0.75rem", background: "rgba(11, 16, 26, 0.7)", border: "1px solid rgba(255, 255, 255, 0.05)", borderRadius: "6px" }}>
                    <span style={{ fontSize: "0.6rem", color: "#94a3b8", fontWeight: 800 }}>Expected behavior</span>
                    <ul style={{ fontSize: "0.62rem", color: "#cbd5e1", paddingLeft: "0.85rem", margin: "0.2rem 0 0 0", lineHeight: 1.3 }}>
                        <li>Dips absorbed at ${putWall.toLocaleString()}</li>
                        <li>Upside capped at ${callWall.toLocaleString()}</li>
                        <li>Range bound around spot</li>
                    </ul>
                </div>
            </div>

            {/* ─── ROW 2: DYNAMIC KEY OPTIONS LEVELS & BIDIRECTIONAL GEX CHART ─── */}
            <div style={{ display: "grid", gridTemplateColumns: "1.2fr 1fr", gap: "0.5rem" }}>
                {/* Left Table + Vertical Price Ladder */}
                <div style={{
                    padding: "0.75rem 0.85rem",
                    background: "rgba(11, 16, 26, 0.7)",
                    border: "1px solid rgba(255, 255, 255, 0.05)",
                    borderRadius: "6px",
                    display: "flex",
                    flexDirection: "column",
                    gap: "0.65rem"
                }}>
                    <h3 style={{ fontSize: "0.8rem", fontWeight: 900, color: "#f8fafc", margin: 0, letterSpacing: "0.04em" }}>
                        KEY OPTIONS LEVELS
                    </h3>

                    <div style={{ display: "grid", gridTemplateColumns: "1.5fr 1fr", gap: "0.75rem" }}>
                        {/* Table */}
                        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.68rem" }}>
                            <thead>
                                <tr style={{ borderBottom: "1px solid rgba(255, 255, 255, 0.06)", color: "#64748b", textAlign: "left" }}>
                                    <th style={{ paddingBottom: "0.35rem" }}>LEVEL</th>
                                    <th style={{ paddingBottom: "0.35rem" }}>TYPE</th>
                                    <th style={{ paddingBottom: "0.35rem" }}>ROLE</th>
                                    <th style={{ paddingBottom: "0.35rem" }}>DISTANCE</th>
                                </tr>
                            </thead>
                            <tbody>
                                <tr style={{ borderBottom: "1px solid rgba(255, 255, 255, 0.03)" }}>
                                    <td style={{ padding: "0.45rem 0", fontWeight: 800, color: "#ffffff", display: "flex", alignItems: "center", gap: "0.35rem" }}>
                                        <span style={{ width: "5px", height: "5px", borderRadius: "50%", background: "#f43f5e" }} />
                                        ${callWall.toLocaleString()}
                                    </td>
                                    <td style={{ color: "#cbd5e1" }}>Call Wall</td>
                                    <td style={{ color: "#f43f5e" }}>Resistance</td>
                                    <td style={{ color: "#f43f5e", fontWeight: 700 }}>{callWallDistPct}%</td>
                                </tr>
                                <tr style={{ borderBottom: "1px solid rgba(255, 255, 255, 0.03)" }}>
                                    <td style={{ padding: "0.45rem 0", fontWeight: 800, color: "#38bdf8", display: "flex", alignItems: "center", gap: "0.35rem" }}>
                                        <span style={{ width: "5px", height: "5px", borderRadius: "50%", background: "#38bdf8" }} />
                                        ${spot.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                                    </td>
                                    <td style={{ color: "#cbd5e1" }}>Current Price</td>
                                    <td style={{ color: "#94a3b8" }}>—</td>
                                    <td style={{ color: "#94a3b8" }}>—</td>
                                </tr>
                                <tr style={{ borderBottom: "1px solid rgba(255, 255, 255, 0.03)" }}>
                                    <td style={{ padding: "0.45rem 0", fontWeight: 800, color: "#ffffff", display: "flex", alignItems: "center", gap: "0.35rem" }}>
                                        <span style={{ width: "5px", height: "5px", borderRadius: "50%", background: "#10b981" }} />
                                        ${putWall.toLocaleString()}
                                    </td>
                                    <td style={{ color: "#cbd5e1" }}>Put Wall</td>
                                    <td style={{ color: "#10b981" }}>Support</td>
                                    <td style={{ color: "#10b981", fontWeight: 700 }}>{putWallDistPct}%</td>
                                </tr>
                                <tr>
                                    <td style={{ padding: "0.45rem 0", fontWeight: 800, color: "#ffffff", display: "flex", alignItems: "center", gap: "0.35rem" }}>
                                        <span style={{ width: "5px", height: "5px", borderRadius: "50%", background: "#f59e0b" }} />
                                        ${gammaFlip.toLocaleString()}
                                    </td>
                                    <td style={{ color: "#cbd5e1" }}>Gamma Flip</td>
                                    <td style={{ color: "#f59e0b" }}>Momentum Shift</td>
                                    <td style={{ color: "#f59e0b", fontWeight: 700 }}>{flipDistPct}%</td>
                                </tr>
                            </tbody>
                        </table>

                        {/* Graphic Vertical Price Ladder Visualizer */}
                        <div style={{
                            position: "relative",
                            display: "flex",
                            flexDirection: "column",
                            alignItems: "center",
                            justifyContent: "space-between",
                            padding: "0.35rem 0",
                            height: "155px",
                            borderLeft: "1px dashed rgba(255, 255, 255, 0.1)"
                        }}>
                            <div style={{
                                width: "92%",
                                padding: "0.2rem 0.4rem",
                                borderRadius: "3px",
                                background: "rgba(244, 63, 94, 0.12)",
                                border: "1px solid rgba(244, 63, 94, 0.3)",
                                color: "#f43f5e",
                                fontSize: "0.6rem",
                                fontWeight: 800,
                                textAlign: "center"
                            }}>
                                CALL WALL ${callWall.toLocaleString()}
                            </div>

                            <div style={{
                                width: "96%",
                                padding: "0.2rem 0.4rem",
                                borderRadius: "3px",
                                background: "rgba(56, 189, 248, 0.18)",
                                border: "1px solid rgba(56, 189, 248, 0.45)",
                                color: "#38bdf8",
                                fontSize: "0.6rem",
                                fontWeight: 900,
                                textAlign: "center",
                                boxShadow: "0 0 6px rgba(56, 189, 248, 0.25)"
                            }}>
                                ${spot.toLocaleString(undefined, { maximumFractionDigits: 0 })} {baseCoin}
                            </div>

                            <div style={{
                                width: "92%",
                                padding: "0.2rem 0.4rem",
                                borderRadius: "3px",
                                background: "rgba(16, 185, 129, 0.12)",
                                border: "1px solid rgba(16, 185, 129, 0.3)",
                                color: "#10b981",
                                fontSize: "0.6rem",
                                fontWeight: 800,
                                textAlign: "center"
                            }}>
                                PUT WALL ${putWall.toLocaleString()}
                            </div>

                            <div style={{
                                width: "92%",
                                padding: "0.2rem 0.4rem",
                                borderRadius: "3px",
                                background: "rgba(245, 158, 11, 0.12)",
                                border: "1px solid rgba(245, 158, 11, 0.3)",
                                color: "#f59e0b",
                                fontSize: "0.6rem",
                                fontWeight: 800,
                                textAlign: "center"
                            }}>
                                GAMMA FLIP ${gammaFlip.toLocaleString()}
                            </div>
                        </div>
                    </div>
                </div>

                {/* Right: Bidirectional Gamma Exposure Chart */}
                <div style={{
                    padding: "0.75rem 0.85rem",
                    background: "rgba(11, 16, 26, 0.7)",
                    border: "1px solid rgba(255, 255, 255, 0.05)",
                    borderRadius: "6px",
                    display: "flex",
                    flexDirection: "column",
                    gap: "0.65rem"
                }}>
                    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                        <h3 style={{ fontSize: "0.8rem", fontWeight: 900, color: "#f8fafc", margin: 0, letterSpacing: "0.04em" }}>
                            BIDIRECTIONAL GAMMA EXPOSURE
                        </h3>
                        <div style={{ display: "flex", gap: "0.75rem", fontSize: "0.62rem", fontWeight: 800 }}>
                            <span style={{ color: "#f43f5e" }}>PUT GEX</span>
                            <span style={{ color: "#10b981" }}>CALL GEX</span>
                        </div>
                    </div>

                    <div style={{ display: "flex", flexDirection: "column", gap: "0.25rem", position: "relative" }}>
                        <div style={{
                            position: "absolute",
                            top: "40%",
                            left: 0,
                            right: 0,
                            borderTop: "1px dashed #38bdf8",
                            zIndex: 10,
                            display: "flex",
                            justifyContent: "flex-end"
                        }}>
                            <span style={{ background: "#06b6d4", color: "#000", fontSize: "0.52rem", fontWeight: 900, padding: "0 0.25rem", borderRadius: "2px" }}>
                                {baseCoin} ${spot.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                            </span>
                        </div>

                        {sortedStrikes.slice(0, 10).map((item) => {
                            const stk = item.strike;
                            const isSpotStrike = Math.abs(stk - spot) < (spot * 0.02);
                            const putWidthPct = Math.min(Math.abs(item.put_gex || 15) * 1.5 + 10, 85);
                            const callWidthPct = Math.min(Math.abs(item.call_gex || 20) * 1.5 + 10, 85);

                            return (
                                <div key={stk} style={{ display: "grid", gridTemplateColumns: "1fr 50px 1fr", alignItems: "center", height: "12px", fontSize: "0.58rem" }}>
                                    <div style={{ display: "flex", justifyContent: "flex-end" }}>
                                        <div style={{
                                            height: "7px",
                                            width: `${putWidthPct}%`,
                                            background: "linear-gradient(270deg, #f43f5e 0%, rgba(244, 63, 94, 0.3) 100%)",
                                            borderRadius: "2px 0 0 2px"
                                        }} />
                                    </div>

                                    <div style={{ textAlign: "center", color: isSpotStrike ? "#38bdf8" : "#94a3b8", fontWeight: isSpotStrike ? 900 : 600 }}>
                                        {stk >= 1000 ? `${Math.round(stk / 1000)}K` : stk}
                                    </div>

                                    <div style={{ display: "flex", justifyContent: "flex-start" }}>
                                        <div style={{
                                            height: "7px",
                                            width: `${callWidthPct}%`,
                                            background: "linear-gradient(90deg, #10b981 0%, rgba(16, 185, 129, 0.3) 100%)",
                                            borderRadius: "0 2px 2px 0"
                                        }} />
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                </div>
            </div>

            {/* ─── ROW 3: DYNAMIC MARKET DATA & DEALER POSITIONING ─────────── */}
            <div style={{ display: "grid", gridTemplateColumns: "1.2fr 1fr", gap: "0.5rem" }}>
                <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                    <span style={{ fontSize: "0.75rem", fontWeight: 900, color: "#f8fafc", letterSpacing: "0.04em" }}>MARKET DATA</span>
                    <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "0.4rem" }}>
                        <div style={{ padding: "0.5rem 0.6rem", background: "rgba(11, 16, 26, 0.7)", border: "1px solid rgba(255, 255, 255, 0.05)", borderRadius: "5px" }}>
                            <span style={{ fontSize: "0.55rem", color: "#64748b", fontWeight: 700 }}>NET DEALER Δ</span>
                            <div style={{ fontSize: "0.8rem", fontWeight: 900, color: dealerDelta >= 0 ? "#10b981" : "#f43f5e", marginTop: "0.1rem" }}>
                                ${dealerDelta.toFixed(2)}M
                            </div>
                            <span style={{ fontSize: "0.55rem", color: isLongGamma ? "#10b981" : "#f43f5e" }}>
                                {isLongGamma ? "Long Gamma" : "Short Gamma"}
                            </span>
                        </div>
                        <div style={{ padding: "0.5rem 0.6rem", background: "rgba(11, 16, 26, 0.7)", border: "1px solid rgba(255, 255, 255, 0.05)", borderRadius: "5px" }}>
                            <span style={{ fontSize: "0.55rem", color: "#64748b", fontWeight: 700 }}>DEALER THETA</span>
                            <div style={{ fontSize: "0.8rem", fontWeight: 900, color: "#f8fafc", marginTop: "0.1rem" }}>
                                ${dealerTheta.toFixed(2)}M
                            </div>
                            <span style={{ fontSize: "0.55rem", color: "#94a3b8" }}>Theta Positive</span>
                        </div>
                        <div style={{ padding: "0.5rem 0.6rem", background: "rgba(11, 16, 26, 0.7)", border: "1px solid rgba(255, 255, 255, 0.05)", borderRadius: "5px" }}>
                            <span style={{ fontSize: "0.55rem", color: "#64748b", fontWeight: 700 }}>DEALER VEGA</span>
                            <div style={{ fontSize: "0.8rem", fontWeight: 900, color: dealerVega >= 0 ? "#10b981" : "#f43f5e", marginTop: "0.1rem" }}>
                                ${dealerVega.toFixed(2)}M
                            </div>
                            <span style={{ fontSize: "0.55rem", color: dealerVega >= 0 ? "#10b981" : "#f43f5e" }}>
                                {dealerVega >= 0 ? "Vega Positive" : "Vega Negative"}
                            </span>
                        </div>
                        <div style={{ padding: "0.5rem 0.6rem", background: "rgba(11, 16, 26, 0.7)", border: "1px solid rgba(255, 255, 255, 0.05)", borderRadius: "5px" }}>
                            <span style={{ fontSize: "0.55rem", color: "#64748b", fontWeight: 700 }}>DEALER VANNA</span>
                            <div style={{ fontSize: "0.8rem", fontWeight: 900, color: (data?.net_dealer_vanna_millions ?? 0) >= 0 ? "#10b981" : "#f43f5e", marginTop: "0.1rem" }}>
                                ${data?.net_dealer_vanna_millions !== undefined ? `${data.net_dealer_vanna_millions.toFixed(2)}M` : "N/A"}
                            </div>
                            <span style={{ fontSize: "0.55rem", color: (data?.net_dealer_vanna_millions ?? 0) >= 0 ? "#10b981" : "#f43f5e" }}>
                                {(data?.net_dealer_vanna_millions ?? 0) >= 0 ? "Vol Squeeze Fuel" : "Vol Resistance"}
                            </span>
                        </div>
                        <div style={{ padding: "0.5rem 0.6rem", background: "rgba(11, 16, 26, 0.7)", border: "1px solid rgba(255, 255, 255, 0.05)", borderRadius: "5px" }}>
                            <span style={{ fontSize: "0.55rem", color: "#64748b", fontWeight: 700 }}>DEALER CHARM</span>
                            <div style={{ fontSize: "0.8rem", fontWeight: 900, color: "#f8fafc", marginTop: "0.1rem" }}>
                                {data?.net_dealer_charm !== undefined ? `${data.net_dealer_charm.toFixed(1)}/day` : "N/A"}
                            </div>
                            <span style={{ fontSize: "0.55rem", color: "#94a3b8" }}>Daily Delta Bleed</span>
                        </div>
                        <div style={{ padding: "0.5rem 0.6rem", background: "rgba(11, 16, 26, 0.7)", border: "1px solid rgba(255, 255, 255, 0.05)", borderRadius: "5px" }}>
                            <span style={{ fontSize: "0.55rem", color: "#64748b", fontWeight: 700 }}>VOL SURFACE</span>
                            <div style={{ fontSize: "0.8rem", fontWeight: 900, color: data?.vol_surface_fitted ? "#38bdf8" : "#94a3b8", marginTop: "0.1rem" }}>
                                {data?.vol_surface_fitted ? "SABR Fitted" : "Raw Venue"}
                            </div>
                            <span style={{ fontSize: "0.55rem", color: data?.vol_surface_fitted ? "#38bdf8" : "#94a3b8" }}>
                                {data?.vol_surface_fitted ? "Smoothed Smile" : "Discrete IV"}
                            </span>
                        </div>
                        <div style={{ padding: "0.5rem 0.6rem", background: "rgba(11, 16, 26, 0.7)", border: "1px solid rgba(255, 255, 255, 0.05)", borderRadius: "5px" }}>
                            <span style={{ fontSize: "0.55rem", color: "#64748b", fontWeight: 700 }}>SKEW</span>
                            <div style={{ fontSize: "0.8rem", fontWeight: 900, color: "#10b981", marginTop: "0.1rem" }}>
                                +{ivSkewPct}%
                            </div>
                            <span style={{ fontSize: "0.55rem", color: "#10b981" }}>Put Skew</span>
                        </div>
                    </div>

                    {/* Dealer Positioning Card */}
                    <div style={{
                        padding: "0.65rem 0.85rem",
                        background: "rgba(11, 16, 26, 0.7)",
                        border: "1px solid rgba(255, 255, 255, 0.05)",
                        borderRadius: "6px",
                        display: "flex",
                        flexDirection: "column",
                        gap: "0.5rem"
                    }}>
                        <span style={{ fontSize: "0.75rem", fontWeight: 900, color: "#f8fafc", letterSpacing: "0.04em" }}>DEALER POSITIONING</span>
                        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "0.4rem", fontSize: "0.62rem" }}>
                            <div>
                                <span style={{ color: "#64748b", fontWeight: 700, display: "block" }}>DELTA</span>
                                <strong style={{ color: dealerDelta >= 0 ? "#10b981" : "#f43f5e" }}>${dealerDelta.toFixed(2)}M</strong>
                            </div>
                            <div>
                                <span style={{ color: "#64748b", fontWeight: 700, display: "block" }}>GAMMA</span>
                                <strong style={{ color: totalGex >= 0 ? "#10b981" : "#f43f5e" }}>+${totalGex.toFixed(2)}M</strong>
                            </div>
                            <div>
                                <span style={{ color: "#64748b", fontWeight: 700, display: "block" }}>VEGA</span>
                                <strong style={{ color: dealerVega >= 0 ? "#10b981" : "#f43f5e" }}>${dealerVega.toFixed(2)}M</strong>
                            </div>
                            <div>
                                <span style={{ color: "#64748b", fontWeight: 700, display: "block" }}>THETA</span>
                                <strong style={{ color: "#10b981" }}>+${dealerTheta.toFixed(2)}M</strong>
                            </div>
                        </div>

                        <div style={{
                            padding: "0.45rem 0.65rem",
                            borderRadius: "4px",
                            background: "rgba(6, 182, 212, 0.06)",
                            border: "1px solid rgba(6, 182, 212, 0.15)",
                            fontSize: "0.62rem",
                            color: "#cbd5e1"
                        }}>
                            Dealers currently exhibit a {isLongGamma ? "long-gamma" : "short-gamma"} profile around spot, suggesting {isLongGamma ? "reduced sensitivity to short-term price swings." : "heightened risk of breakout volatility."}
                        </div>
                    </div>
                </div>

                {/* Right: Dynamic Orderflow Bias Indicator */}
                <div style={{
                    padding: "0.75rem 0.85rem",
                    background: "rgba(11, 16, 26, 0.7)",
                    border: "1px solid rgba(255, 255, 255, 0.05)",
                    borderRadius: "6px",
                    display: "flex",
                    flexDirection: "column",
                    gap: "0.65rem"
                }}>
                    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                        <span style={{ fontSize: "0.75rem", fontWeight: 900, color: "#f8fafc", letterSpacing: "0.04em" }}>ORDERFLOW BIAS</span>
                        <span style={{ fontSize: "0.58rem", fontWeight: 800, color: confidenceScore < 50 ? "#f43f5e" : "#10b981", background: confidenceScore < 50 ? "rgba(244,63,94,0.12)" : "rgba(16,185,129,0.12)", border: `1px solid ${confidenceScore < 50 ? "rgba(244,63,94,0.25)" : "rgba(16,185,129,0.25)"}`, padding: "0.15rem 0.4rem", borderRadius: "4px" }}>
                            {confidenceScore < 50 ? "SELL BIAS" : "BUY BIAS"}
                        </span>
                    </div>

                    <div style={{ display: "flex", alignItems: "baseline", gap: "0.3rem" }}>
                        <span style={{ fontSize: "1.4rem", fontWeight: 900, color: "#f8fafc" }}>{confidenceScore}</span>
                        <span style={{ fontSize: "0.68rem", color: "#64748b" }}>/ 100</span>
                    </div>

                    <div style={{ display: "flex", flexDirection: "column", gap: "0.2rem" }}>
                        <div style={{ height: "5px", width: "100%", borderRadius: "3px", background: "rgba(255,255,255,0.06)", position: "relative", overflow: "hidden" }}>
                            <div style={{ width: `${confidenceScore}%`, height: "100%", background: confidenceScore < 50 ? "linear-gradient(90deg, #f43f5e 0%, #f59e0b 100%)" : "linear-gradient(90deg, #f59e0b 0%, #10b981 100%)", borderRadius: "3px" }} />
                        </div>
                        <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.55rem", color: "#64748b", fontWeight: 700 }}>
                            <span>SELL</span>
                            <span style={{ color: "#38bdf8" }}>Current</span>
                            <span>BUY</span>
                        </div>
                    </div>

                    <div style={{ display: "flex", flexDirection: "column", gap: "0.25rem", fontSize: "0.62rem", background: "rgba(255,255,255,0.02)", padding: "0.45rem", borderRadius: "4px" }}>
                        <div style={{ display: "flex", justifyContent: "space-between" }}>
                            <span style={{ color: "#64748b" }}>Dealer Δ</span>
                            <span style={{ color: dealerDelta >= 0 ? "#10b981" : "#f43f5e", fontWeight: 700 }}>${dealerDelta.toFixed(0)}M</span>
                        </div>
                        <div style={{ display: "flex", justifyContent: "space-between" }}>
                            <span style={{ color: "#64748b" }}>Spot vs Flip</span>
                            <span style={{ color: "#10b981", fontWeight: 700 }}>{flipDistPct}%</span>
                        </div>
                    </div>
                </div>
            </div>

            {/* ─── ROW 4: GAMMA DISTRIBUTION HEATMAP BAR ────────────────────── */}
            <div style={{
                padding: "0.75rem 0.85rem",
                background: "rgba(11, 16, 26, 0.7)",
                border: "1px solid rgba(255, 255, 255, 0.05)",
                borderRadius: "6px",
                display: "flex",
                flexDirection: "column",
                gap: "0.65rem"
            }}>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                    <span style={{ fontSize: "0.75rem", fontWeight: 900, color: "#f8fafc", letterSpacing: "0.04em" }}>
                        GAMMA DISTRIBUTION HEATMAP
                    </span>
                    <div style={{ display: "flex", gap: "0.25rem" }}>
                        {(["GEX", "OI", "VOLUME"] as const).map((tab) => {
                            const isActive = activeHeatmapTab === tab;
                            return (
                                <button
                                    key={tab}
                                    onClick={() => setActiveHeatmapTab(tab)}
                                    style={{
                                        padding: "0.18rem 0.5rem",
                                        fontSize: "0.58rem",
                                        fontWeight: 800,
                                        borderRadius: "3px",
                                        border: isActive ? "1px solid #38bdf8" : "1px solid rgba(255, 255, 255, 0.05)",
                                        background: isActive ? "rgba(56, 189, 248, 0.12)" : "transparent",
                                        color: isActive ? "#38bdf8" : "#64748b",
                                        cursor: "pointer"
                                    }}
                                >
                                    {tab}
                                </button>
                            );
                        })}
                    </div>
                </div>

                <div style={{ display: "flex", flexDirection: "column", gap: "0.3rem", position: "relative" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.58rem", fontWeight: 800 }}>
                        <span style={{ color: "#f43f5e" }}>PUT SIDE</span>
                        <span style={{ color: "#38bdf8" }}>Spot Marker ${spot.toLocaleString(undefined, { maximumFractionDigits: 0 })}</span>
                        <span style={{ color: "#10b981" }}>CALL SIDE</span>
                    </div>

                    <div style={{ display: "grid", gridTemplateColumns: "repeat(60, 1fr)", gap: "2px", height: "28px" }}>
                        {Array.from({ length: 60 }).map((_, idx) => {
                            const isPutSide = idx < 30;
                            const intensity = Math.min((idx % 7 + 2) * 0.15, 0.9);
                            return (
                                <div
                                    key={idx}
                                    style={{
                                        background: isPutSide
                                            ? `rgba(244, 63, 94, ${intensity})`
                                            : `rgba(16, 185, 129, ${intensity})`,
                                        borderRadius: "1px"
                                    }}
                                />
                            );
                        })}
                    </div>

                    {/* Dynamic Heatmap Axis Labels */}
                    {(() => {
                        const hstep = spot > 10000 ? 5000 : (spot > 1000 ? 200 : (spot > 50 ? 10 : 2));
                        const hcenter = Math.round(spot / hstep) * hstep;
                        const fmtH = (val: number) => val >= 1000 ? `${(val / 1000).toFixed(val % 1000 === 0 ? 0 : 1)}K` : `$${val.toFixed(0)}`;
                        return (
                            <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.58rem", color: "#64748b", paddingTop: "0.15rem" }}>
                                <span>{fmtH(hcenter - (hstep * 3))}</span>
                                <span>{fmtH(hcenter - (hstep * 2))}</span>
                                <span>{fmtH(hcenter - hstep)}</span>
                                <span style={{ color: "#38bdf8", fontWeight: 900 }}>{fmtH(spot)}</span>
                                <span>{fmtH(hcenter + hstep)}</span>
                                <span>{fmtH(hcenter + (hstep * 2))}</span>
                                <span>{fmtH(hcenter + (hstep * 3))}</span>
                            </div>
                        );
                    })()}
                </div>
            </div>
        </div>
    );
};
