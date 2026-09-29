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
    regime: "LONG_GAMMA_STABLE" | "SHORT_GAMMA_VOLATILE" | "UNAVAILABLE";
    options_available?: boolean;
    computed_at?: number;
    message?: string;
    gex_curve: GexStrikeItem[];
    venue_metrics?: VenueMetrics;
    max_pain?: number | null;
    skew?: { rr25_pct: number; fly25_pct: number; ref_expiry: string } | null;
    expiry_clusters?: Array<{
        expiry: string; dte: number; total_oi_usd: number;
        call_oi_usd: number; put_oi_usd: number; share_pct: number;
    }>;
    hedging_profile?: {
        bias: string; downside_support_gex_m: number; upside_resistance_gex_m: number;
        top_supportive: Array<{ strike: number; gex_m: number }>;
        top_suppressive: Array<{ strike: number; gex_m: number }>;
    } | null;
    pin_map?: Array<{ strike: number; gex_m: number; dist_pct: number; strength: number }>;
    oi_flow?: {
        hours: number; delta_total_usd: number; delta_call_usd: number; delta_put_usd: number;
        top_strikes: Array<{ strike: number; delta_oi_usd: number; side: string }>;
    } | null;
    confidence?: { score: number; grade: string; reasons: string[] } | null;
    regime_transitions?: Array<{ ts: number; from: string; to: string; spot: number }>;
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
    // Everything below renders from REAL engine output only. The fabricated
    // per-coin fallbacks that used to live here (spot 85875.50, walls at
    // spot±15%, dealer delta -514.64M, a canned GEX curve) made the page look
    // alive while showing fiction whenever the backend had no data.
    const hasData = !!data && data.options_available !== false && !!data.spot_price;
    const spot = liveSpotPrice || (data?.spot_price ?? 0);
    const callWall = data?.call_wall ?? 0;
    const putWall = data?.put_wall ?? 0;
    const gammaFlip = data?.gamma_flip ?? 0;
    const totalGex = data?.total_net_gex_millions ?? 0;
    const isLongGamma = totalGex >= 0;

    // Dynamic distance calculations relative to live spot
    const callWallDistVal = ((callWall - spot) / spot * 100);
    const putWallDistVal = ((putWall - spot) / spot * 100);
    const flipDistVal = ((gammaFlip - spot) / spot * 100);

    const callWallDistPct = (callWallDistVal >= 0 ? "+" : "") + callWallDistVal.toFixed(1);
    const putWallDistPct = (putWallDistVal >= 0 ? "+" : "") + putWallDistVal.toFixed(1);
    const flipDistPct = (flipDistVal >= 0 ? "+" : "") + flipDistVal.toFixed(1);

    const dealerDelta = data?.net_dealer_delta_millions ?? 0;
    const dealerTheta = data?.net_dealer_theta ?? 0;
    const dealerVega = data?.net_dealer_vega ?? 0;
    // Backend sends iv_skew already scaled to percent (round(skew*100, 2)).
    const ivSkewVal = typeof data?.iv_skew === "number" ? data.iv_skew : 0;
    const ivSkewPct = (ivSkewVal >= 0 ? "+" : "") + ivSkewVal.toFixed(2);

    // Orderflow confidence: real backend confluence score, or neutral when the
    // orderflow accumulator has not produced one — never a synthesized number.
    const backendScore = hasData ? data?.orderflow?.confluence_score : undefined;
    const confidenceScore = backendScore != null ? Math.min(100, Math.max(0, Math.round(backendScore))) : 50;

    // GEX curve: real engine strikes only. The canned curve that used to be
    // drawn here (fixed net_gex values, invented OI) looked identical whether
    // or not the backend had returned a single real contract.
    const gexCurve = data?.gex_curve ?? [];

    // Freshness: gamma levels only refresh with the options board (~15-30s
    // venue cache) while the spot ticker ticks every 2s — label data age
    // honestly instead of always claiming LIVE REAL-TIME.
    const dataAgeSec = hasData && data?.computed_at
        ? Math.max(0, Math.floor(Date.now() / 1000 - data.computed_at))
        : null;
    const dataStatus: "OFFLINE" | "STALE" | "LIVE" =
        !hasData ? "OFFLINE" : dataAgeSec === null || dataAgeSec > 120 ? "STALE" : "LIVE";

    const sortedStrikes = [...gexCurve].sort((a, b) => b.strike - a.strike);

    // ─── INSTITUTIONAL ANALYTICS (all backend-computed, real data only) ────
    const maxPain = hasData ? data?.max_pain ?? null : null;
    const pinMap = hasData ? data?.pin_map ?? [] : [];
    const allClusters = hasData ? data?.expiry_clusters ?? [] : [];
    const clusters = allClusters.filter((c) => c.expiry !== "_0DTE_SHARE").slice(0, 3);
    const zeroDteShare = allClusters.find((c) => c.expiry === "_0DTE_SHARE")?.share_pct ?? null;
    const hedging = hasData ? data?.hedging_profile ?? null : null;
    const oiFlow = hasData ? data?.oi_flow ?? null : null;
    const skewMetrics = hasData ? data?.skew ?? null : null;
    const transitions = hasData ? (data?.regime_transitions ?? []).slice(-4).reverse() : [];
    const confidence = hasData ? data?.confidence ?? null : null;
    const fmtNotional = (v: number) =>
        Math.abs(v) >= 1e9 ? `$${(v / 1e9).toFixed(1)}B` : `$${(v / 1e6).toFixed(0)}M`;
    const fmtSignedM = (v: number) => `${v >= 0 ? "+" : "−"}$${Math.abs(v).toFixed(1)}M`;
    const flipTime = (ts: number) =>
        new Date(ts * 1000).toLocaleTimeString("en-GB", { timeZone: "Africa/Nairobi", hour: "2-digit", minute: "2-digit" });

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
                            {spot > 0 ? `$${spot.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : "—"}
                        </span>
                        {spot > 0 && (
                        <span style={{ fontSize: "0.7rem", fontWeight: 800, color: "#64748b" }}>
                            {isLongGamma ? "LONG Γ" : "SHORT Γ"}
                        </span>
                        )}
                    </div>
                </div>

                <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
                    {hasData && (
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
                    )}

                    <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                        <div style={{
                            display: "flex",
                            alignItems: "center",
                            gap: "0.3rem",
                            padding: "0.25rem 0.5rem",
                            borderRadius: "4px",
                            background: dataStatus === "LIVE" ? "rgba(16, 185, 129, 0.12)" : dataStatus === "STALE" ? "rgba(245, 158, 11, 0.12)" : "rgba(100, 116, 139, 0.12)",
                            border: `1px solid ${dataStatus === "LIVE" ? "rgba(16, 185, 129, 0.25)" : dataStatus === "STALE" ? "rgba(245, 158, 11, 0.3)" : "rgba(100, 116, 139, 0.3)"}`,
                            color: dataStatus === "LIVE" ? "#10b981" : dataStatus === "STALE" ? "#f59e0b" : "#94a3b8",
                            fontSize: "0.65rem",
                            fontWeight: 800
                        }}>
                            <span style={{ width: "5px", height: "5px", borderRadius: "50%", background: dataStatus === "LIVE" ? "#10b981" : dataStatus === "STALE" ? "#f59e0b" : "#94a3b8" }} />
                            {dataStatus === "LIVE" ? "LIVE REAL-TIME" : dataStatus === "STALE" ? `STALE ${dataAgeSec ?? ""}s` : "NO DATA"}
                        </div>

                        {confidence && (
                            <div
                                title={confidence.reasons.join(" · ")}
                                style={{
                                    display: "flex", alignItems: "center", gap: "0.3rem",
                                    padding: "0.25rem 0.5rem", borderRadius: "4px", fontSize: "0.65rem", fontWeight: 800,
                                    background: confidence.score >= 80 ? "rgba(16, 185, 129, 0.12)" : confidence.score >= 50 ? "rgba(245, 158, 11, 0.12)" : "rgba(244, 63, 94, 0.12)",
                                    border: `1px solid ${confidence.score >= 80 ? "rgba(16, 185, 129, 0.25)" : confidence.score >= 50 ? "rgba(245, 158, 11, 0.3)" : "rgba(244, 63, 94, 0.3)"}`,
                                    color: confidence.score >= 80 ? "#10b981" : confidence.score >= 50 ? "#f59e0b" : "#f43f5e",
                                }}
                            >
                                DATA GRADE {confidence.grade} · {confidence.score}/100
                            </div>
                        )}

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

            {/* ─── NO OPTIONS MARKET BANNER (honest empty state) ────────────── */}
            {data && data.options_available === false && (
                <div style={{
                    padding: "0.55rem 0.85rem",
                    background: "rgba(100, 116, 139, 0.08)",
                    border: "1px solid rgba(100, 116, 139, 0.3)",
                    borderRadius: "6px",
                    display: "flex",
                    alignItems: "center",
                    gap: "0.5rem",
                    fontSize: "0.68rem",
                    color: "#94a3b8",
                }}>
                    <span style={{ fontSize: "0.85rem" }}>ℹ</span>
                    <span>
                        <strong>No options market data for {baseCoin}.</strong>{" "}
                        {data.message || "GEX levels, walls and dealer positioning need a listed options chain (currently BTC, ETH, SOL, AVAX). Values are withheld rather than estimated."}
                    </span>
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

                {hasData && (
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
                            PUT SKEW {ivSkewPct}%
                        </span>
                    </div>
                </div>
                )}
            </div>

            {/* 4 Dynamic Intelligence Cards */}
            <div style={{ display: hasData ? "grid" : "none", gridTemplateColumns: "repeat(4, 1fr)", gap: "0.5rem" }}>
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

            {/* ─── ROW 1.5: DEALER HEDGING PRESSURE · SKEW · 24H FLOW ─────── */}
            <div style={{ display: hasData ? "grid" : "none", gridTemplateColumns: "repeat(3, 1fr)", gap: "0.5rem" }}>
                <div style={{ padding: "0.65rem 0.75rem", background: "rgba(11, 16, 26, 0.7)", border: "1px solid rgba(255, 255, 255, 0.05)", borderRadius: "6px" }}>
                    <span style={{ fontSize: "0.62rem", fontWeight: 800, color: "#64748b" }}>DEALER HEDGING PRESSURE (±5% band)</span>
                    {hedging ? (
                        <>
                            <div style={{ fontSize: "0.95rem", fontWeight: 900, marginTop: "0.25rem", color: hedging.bias === "SUPPORTIVE" ? "#10b981" : hedging.bias === "SUPPRESSIVE" ? "#f43f5e" : "#94a3b8" }}>
                                {hedging.bias}
                            </div>
                            <div style={{ display: "flex", gap: "0.8rem", fontSize: "0.6rem", color: "#cbd5e1", marginTop: "0.2rem" }}>
                                <span>Support <strong style={{ color: "#10b981" }}>{fmtSignedM(hedging.downside_support_gex_m)}</strong></span>
                                <span>Resist <strong style={{ color: "#f43f5e" }}>{fmtSignedM(hedging.upside_resistance_gex_m)}</strong></span>
                            </div>
                            <div style={{ fontSize: "0.58rem", color: "#64748b", marginTop: "0.25rem" }}>
                                {hedging.top_supportive.length > 0 && `Dip-buy wall: $${hedging.top_supportive[0].strike.toLocaleString()} (${fmtSignedM(hedging.top_supportive[0].gex_m)})`}
                                {hedging.top_suppressive.length > 0 && ` · Rally-sell wall: $${hedging.top_suppressive[0].strike.toLocaleString()} (${fmtSignedM(hedging.top_suppressive[0].gex_m)})`}
                            </div>
                        </>
                    ) : (
                        <div style={{ fontSize: "0.62rem", color: "#64748b", marginTop: "0.25rem" }}>No hedging data in current board.</div>
                    )}
                </div>

                <div style={{ padding: "0.65rem 0.75rem", background: "rgba(11, 16, 26, 0.7)", border: "1px solid rgba(255, 255, 255, 0.05)", borderRadius: "6px" }}>
                    <span style={{ fontSize: "0.62rem", fontWeight: 800, color: "#64748b" }}>VOL SKEW (25Δ)</span>
                    {skewMetrics ? (
                        <>
                            <div style={{ fontSize: "0.95rem", fontWeight: 900, marginTop: "0.25rem", color: skewMetrics.rr25_pct < 0 ? "#f43f5e" : "#10b981" }}>
                                RR25 {skewMetrics.rr25_pct >= 0 ? "+" : ""}{skewMetrics.rr25_pct.toFixed(2)}%
                            </div>
                            <div style={{ fontSize: "0.6rem", color: "#cbd5e1", marginTop: "0.2rem" }}>
                                Fly25 {skewMetrics.fly25_pct >= 0 ? "+" : ""}{skewMetrics.fly25_pct.toFixed(2)}% · {skewMetrics.ref_expiry}
                            </div>
                            <div style={{ fontSize: "0.58rem", color: "#64748b", marginTop: "0.25rem" }}>
                                {skewMetrics.rr25_pct < 0 ? "Puts bid — crash-hedge demand elevated." : "Calls bid — upside chase demand."}
                            </div>
                        </>
                    ) : (
                        <div style={{ fontSize: "0.62rem", color: "#64748b", marginTop: "0.25rem" }}>Skew needs a two-sided chain — not measurable on this board.</div>
                    )}
                </div>

                <div style={{ padding: "0.65rem 0.75rem", background: "rgba(11, 16, 26, 0.7)", border: "1px solid rgba(255, 255, 255, 0.05)", borderRadius: "6px" }}>
                    <span style={{ fontSize: "0.62rem", fontWeight: 800, color: "#64748b" }}>24H POSITIONING FLOW</span>
                    {oiFlow ? (
                        <>
                            <div style={{ fontSize: "0.95rem", fontWeight: 900, marginTop: "0.25rem", color: oiFlow.delta_total_usd >= 0 ? "#10b981" : "#f43f5e" }}>
                                {fmtSignedM(oiFlow.delta_total_usd / 1e6).replace("M", oiFlow.delta_total_usd >= 1e9 || oiFlow.delta_total_usd <= -1e9 ? "B-scale" : "M")}
                                <span style={{ fontSize: "0.58rem", color: "#64748b", fontWeight: 700 }}> vs {oiFlow.hours}h ago</span>
                            </div>
                            <div style={{ display: "flex", gap: "0.8rem", fontSize: "0.6rem", color: "#cbd5e1", marginTop: "0.2rem" }}>
                                <span>Calls <strong style={{ color: oiFlow.delta_call_usd >= 0 ? "#10b981" : "#f43f5e" }}>{oiFlow.delta_call_usd >= 0 ? "+" : "−"}{fmtNotional(Math.abs(oiFlow.delta_call_usd))}</strong></span>
                                <span>Puts <strong style={{ color: oiFlow.delta_put_usd >= 0 ? "#10b981" : "#f43f5e" }}>{oiFlow.delta_put_usd >= 0 ? "+" : "−"}{fmtNotional(Math.abs(oiFlow.delta_put_usd))}</strong></span>
                            </div>
                            <div style={{ fontSize: "0.58rem", color: "#64748b", marginTop: "0.25rem" }}>
                                {oiFlow.top_strikes.map((s) => `$${s.strike.toLocaleString()} ${s.side}`).join(" · ") || "No notable strike moves."}
                            </div>
                        </>
                    ) : (
                        <div style={{ fontSize: "0.62rem", color: "#64748b", marginTop: "0.25rem" }}>Collecting baseline — flow deltas appear after ~24h of snapshots.</div>
                    )}
                </div>
            </div>

            {/* ─── ROW 1.6: EXPIRY CLUSTERS · MAX PAIN · PIN MAP · REGIME MEMORY ── */}
            <div style={{ display: hasData ? "grid" : "none", gridTemplateColumns: "1.2fr 1fr", gap: "0.5rem" }}>
                <div style={{ padding: "0.65rem 0.75rem", background: "rgba(11, 16, 26, 0.7)", border: "1px solid rgba(255, 255, 255, 0.05)", borderRadius: "6px" }}>
                    <span style={{ fontSize: "0.62rem", fontWeight: 800, color: "#64748b" }}>EXPIRY CLUSTERING (notional OI)</span>
                    {clusters.length > 0 ? (
                        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.62rem", marginTop: "0.3rem" }}>
                            <thead>
                                <tr style={{ color: "#64748b", textAlign: "left", borderBottom: "1px solid rgba(255,255,255,0.06)" }}>
                                    <th style={{ paddingBottom: "0.25rem" }}>EXPIRY</th>
                                    <th>DTE</th>
                                    <th>NOTIONAL</th>
                                    <th>SHARE</th>
                                </tr>
                            </thead>
                            <tbody>
                                {clusters.map((c) => (
                                    <tr key={c.expiry} style={{ borderBottom: "1px solid rgba(255,255,255,0.03)" }}>
                                        <td style={{ padding: "0.25rem 0", fontWeight: 800, color: "#f8fafc" }}>{c.expiry}</td>
                                        <td style={{ color: "#cbd5e1" }}>{c.dte.toFixed(0)}</td>
                                        <td style={{ color: "#38bdf8", fontWeight: 700 }}>{fmtNotional(c.total_oi_usd)}</td>
                                        <td style={{ color: "#94a3b8" }}>{c.share_pct.toFixed(1)}%</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    ) : (
                        <div style={{ fontSize: "0.62rem", color: "#64748b", marginTop: "0.25rem" }}>No expiry notional in current board.</div>
                    )}
                    {zeroDteShare !== null && (
                        <div style={{ fontSize: "0.58rem", color: zeroDteShare > 50 ? "#f59e0b" : "#64748b", marginTop: "0.3rem", fontWeight: 700 }}>
                            0DTE share: {zeroDteShare.toFixed(1)}%{zeroDteShare > 50 ? " — expiry-day regime, pin risk dominates" : ""}
                        </div>
                    )}
                </div>

                <div style={{ padding: "0.65rem 0.75rem", background: "rgba(11, 16, 26, 0.7)", border: "1px solid rgba(255, 255, 255, 0.05)", borderRadius: "6px", display: "flex", flexDirection: "column", gap: "0.4rem" }}>
                    <span style={{ fontSize: "0.62rem", fontWeight: 800, color: "#64748b" }}>MAX PAIN & PIN MAP</span>
                    {maxPain ? (
                        <div style={{ fontSize: "0.72rem", fontWeight: 900, color: "#f59e0b" }}>
                            Max Pain ${maxPain.toLocaleString()}
                            <span style={{ fontSize: "0.58rem", color: "#64748b", fontWeight: 700 }}>
                                {spot > 0 ? ` · ${(Math.abs(maxPain - spot) / spot * 100).toFixed(2)}% from spot` : ""}
                            </span>
                        </div>
                    ) : (
                        <div style={{ fontSize: "0.62rem", color: "#64748b" }}>Max pain needs OI — none in board.</div>
                    )}
                    {pinMap.length > 0 && (
                        <div style={{ display: "flex", flexDirection: "column", gap: "0.2rem" }}>
                            {pinMap.map((p) => (
                                <div key={p.strike} style={{ display: "flex", alignItems: "center", gap: "0.4rem", fontSize: "0.6rem" }}>
                                    <span style={{ width: "64px", color: "#f8fafc", fontWeight: 800 }}>${p.strike.toLocaleString()}</span>
                                    <div style={{ flex: 1, height: "5px", background: "rgba(255,255,255,0.06)", borderRadius: "3px", overflow: "hidden" }}>
                                        <div style={{ width: `${p.strength}%`, height: "100%", background: "#eab308", borderRadius: "3px" }} />
                                    </div>
                                    <span style={{ color: "#64748b" }}>{p.dist_pct.toFixed(1)}% · {p.strength.toFixed(0)}%</span>
                                </div>
                            ))}
                        </div>
                    )}
                    {transitions.length > 0 && (
                        <div style={{ borderTop: "1px solid rgba(255,255,255,0.06)", paddingTop: "0.3rem", fontSize: "0.58rem", color: "#64748b" }}>
                            <span style={{ fontWeight: 800, color: "#94a3b8" }}>REGIME MEMORY · </span>
                            {transitions.map((t, i) => (
                                <span key={t.ts} style={{ color: t.to.includes("LONG") ? "#10b981" : "#f43f5e" }}>
                                    {i > 0 ? " · " : ""}{flipTime(t.ts)} {t.from.includes("LONG") ? "L→S" : "S→L"}
                                </span>
                            ))}
                        </div>
                    )}
                </div>
            </div>

            {/* ─── ROW 2: DYNAMIC KEY OPTIONS LEVELS & BIDIRECTIONAL GEX CHART ─── */}
            <div style={{ display: hasData ? "grid" : "none", gridTemplateColumns: "1.2fr 1fr", gap: "0.5rem" }}>
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
            <div style={{ display: hasData ? "grid" : "none", gridTemplateColumns: "1.2fr 1fr", gap: "0.5rem" }}>
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

            {/* ─── ROW 4: GAMMA DISTRIBUTION HEATMAP BAR (real per-strike data) ── */}
            <div style={{
                display: hasData ? "flex" : "none",
                flexDirection: "column",
                padding: "0.75rem 0.85rem",
                background: "rgba(11, 16, 26, 0.7)",
                border: "1px solid rgba(255, 255, 255, 0.05)",
                borderRadius: "6px",
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

                    {/* Per-strike gamma heat strip driven by the real gex_curve —
                        the deterministic 60-cell color pattern that used to live
                        here rendered the same "data" for every asset and expiry. */}
                    {sortedStrikes.length === 0 ? (
                        <div style={{ fontSize: "0.62rem", color: "#64748b", padding: "0.35rem 0" }}>
                            No per-strike gamma data in the current board.
                        </div>
                    ) : (
                    <div style={{ display: "grid", gridTemplateColumns: `repeat(${Math.min(sortedStrikes.length, 14)}, 1fr)`, gap: "2px", height: "28px" }}>
                        {[...sortedStrikes].reverse().map((item) => {
                            const maxAbs = Math.max(
                                ...sortedStrikes.map((s) => Math.abs(s.net_gex || 0)),
                                1e-9,
                            );
                            const intensity = Math.min(Math.abs(item.net_gex || 0) / maxAbs, 1) * 0.75 + 0.08;
                            const neg = (item.net_gex || 0) < 0;
                            return (
                                <div
                                    key={item.strike}
                                    title={`$${item.strike.toLocaleString()} · net GEX ${item.net_gex}M`}
                                    style={{
                                        background: neg
                                            ? `rgba(244, 63, 94, ${intensity})`
                                            : `rgba(16, 185, 129, ${intensity})`,
                                        borderRadius: "1px"
                                    }}
                                />
                            );
                        })}
                    </div>
                    )}

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
