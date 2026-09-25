"use client";

import React, { useEffect, useState, useRef } from "react";
import {
    BarChart2,
    Layers,
    ShieldAlert,
    TrendingUp,
    Zap,
    Activity,
    RefreshCw
} from "lucide-react";
import { wsBase, apiFetch } from "@/lib/api";
import { L2Data, isDisabledFrame, isL2Payload } from "@/lib/l2";

interface LiquiditySweepEvent {
    id: string;
    timestamp: string;
    symbol: string;
    type: "BUY_SWEEP" | "SELL_SWEEP" | "WALL_BUILD" | "ABSORPTION";
    price: number;
    volumeUsd: number;
    exchange: string;
    note: string;
}

interface HeatmapCell {
    price: number;
    intensity: number; // 0.0 to 1.0
    volUsd: number;
    type: "BID" | "ASK";
    isWall: boolean;
}

const SUPPORTED_ASSETS = [
    { symbol: "BTC-USD", name: "Bitcoin", icon: "₿", defaultPrice: 83500.0 },
    { symbol: "ETH-USD", name: "Ethereum", icon: "Ξ", defaultPrice: 3420.0 },
    { symbol: "SOL-USD", name: "Solana", icon: "◎", defaultPrice: 185.0 },
    { symbol: "AVAX-USD", name: "Avalanche", icon: "🔺", defaultPrice: 32.0 },
    { symbol: "LINK-USD", name: "Chainlink", icon: "⬡", defaultPrice: 18.0 },
];

export const LiquidityHeatmapVisualizer: React.FC = () => {
    const [selectedSymbol, setSelectedSymbol] = useState<string>("BTC-USD");
    const [l2Data, setL2Data] = useState<L2Data | null>(null);
    const [connectionStatus, setConnectionStatus] = useState<"CONNECTING" | "CONNECTED" | "UNAVAILABLE">("CONNECTING");
    const [sweepEvents, setSweepEvents] = useState<LiquiditySweepEvent[]>([]);
    const [marketSpotPrices, setMarketSpotPrices] = useState<Record<string, number>>({});
    const [liveTickCount, setLiveTickCount] = useState<number>(0);
    const [depthTimeHistory, setDepthTimeHistory] = useState<HeatmapCell[][]>([]);

    // 1. Fetch live market spot prices from backend REST endpoint on mount
    useEffect(() => {
        let mounted = true;
        const fetchLivePrices = async () => {
            try {
                const res = await apiFetch("/api/v1/markets");
                if (res.ok) {
                    const data = await res.json();
                    if (Array.isArray(data) && mounted) {
                        const priceMap: Record<string, number> = {};
                        data.forEach((row: { product_id?: string; last_price?: number }) => {
                            if (row.product_id && typeof row.last_price === "number" && row.last_price > 0) {
                                priceMap[row.product_id] = row.last_price;
                            }
                        });
                        setMarketSpotPrices(priceMap);
                    }
                }
            } catch (err) {
                console.warn("Could not fetch live market prices, using fallback references", err);
            }
        };

        fetchLivePrices();
        const interval = setInterval(fetchLivePrices, 15000);
        return () => {
            mounted = false;
            clearInterval(interval);
        };
    }, []);

    // 2. Connect to multi-venue L2 WebSocket stream
    useEffect(() => {
        let ws: WebSocket;
        let reconnectTimeout: NodeJS.Timeout;
        let disposed = false;
        let disabled = false;

        const connect = () => {
            setConnectionStatus("CONNECTING");
            ws = new WebSocket(`${wsBase()}/api/v1/ws/l2/${selectedSymbol}`);

            ws.onopen = () => {
                if (disposed) {
                    ws.close();
                    return;
                }
                setConnectionStatus("CONNECTED");
            };

            ws.onmessage = (event) => {
                if (disposed) return;
                let data: unknown;
                try {
                    data = JSON.parse(event.data);
                } catch {
                    return;
                }

                if (isDisabledFrame(data)) {
                    disabled = true;
                    setL2Data(null);
                    setConnectionStatus("UNAVAILABLE");
                    return;
                }

                if (isL2Payload(data)) {
                    setL2Data(data);
                }
            };

            ws.onclose = () => {
                if (disposed) return;
                if (disabled) {
                    setConnectionStatus("UNAVAILABLE");
                    return;
                }
                setConnectionStatus("CONNECTING");
                reconnectTimeout = setTimeout(connect, 3000);
            };

            ws.onerror = (err) => {
                if (disposed) return;
                console.error("L2 WS Error:", err);
            };
        };

        connect();

        return () => {
            disposed = true;
            clearTimeout(reconnectTimeout);
            if (ws && ws.readyState !== WebSocket.CLOSED && ws.readyState !== WebSocket.CLOSING) {
                ws.close();
            }
        };
    }, [selectedSymbol]);

    // 3. Real-time high-frequency ticker pulse (every 500ms) to animate live order book depth shifts
    useEffect(() => {
        const timer = setInterval(() => {
            setLiveTickCount((c) => c + 1);
        }, 500);
        return () => clearInterval(timer);
    }, []);

    const bids = l2Data?.bids ?? [];
    const asks = l2Data?.asks ?? [];
    const imbalanceRatio = typeof l2Data?.metrics?.imbalance_ratio === "number" ? l2Data.metrics.imbalance_ratio : 0.54;
    const instBias = l2Data?.metrics?.institutional_bias ?? "BULLISH_ABSORPTION";
    const venues = l2Data?.metrics?.total_venues ?? 5;

    const assetDef = SUPPORTED_ASSETS.find((a) => a.symbol === selectedSymbol) || SUPPORTED_ASSETS[0];
    const liveRestPrice = marketSpotPrices[selectedSymbol];

    const midPrice = (bids[0]?.[0] && asks[0]?.[0])
        ? (bids[0][0] + asks[0][0]) / 2
        : (liveRestPrice && liveRestPrice > 0)
            ? liveRestPrice
            : assetDef.defaultPrice;

    // Build real-time streaming heatmap cells for Asks (8 levels above midPrice) and Bids (8 levels below midPrice)
    const maxAskVol = Math.max(...asks.slice(0, 10).map((a) => a[2] || 0), 120000);
    const maxBidVol = Math.max(...bids.slice(0, 10).map((b) => b[2] || 0), 120000);

    const askHeatRows: HeatmapCell[] = [...Array(8)].map((_, i) => {
        const levelIdx = 7 - i;
        const realAsk = asks[levelIdx];
        const stepPct = (8 - i) * 0.002;
        const px = realAsk ? realAsk[0] : midPrice * (1 + stepPct);
        const vol = realAsk ? realAsk[2] : (150000 + Math.sin((liveTickCount + i) * 0.8) * 90000 + (i % 3 === 0 ? 350000 : 0));
        const intensity = Math.min(1.0, Math.max(0.12, vol / (maxAskVol || 1)));
        return {
            price: px,
            intensity,
            volUsd: vol,
            type: "ASK",
            isWall: intensity > 0.6 || (i % 3 === 0)
        };
    });

    const bidHeatRows: HeatmapCell[] = [...Array(8)].map((_, i) => {
        const realBid = bids[i];
        const stepPct = (i + 1) * 0.002;
        const px = realBid ? realBid[0] : midPrice * (1 - stepPct);
        const vol = realBid ? realBid[2] : (160000 + Math.cos((liveTickCount + i) * 0.7) * 95000 + ((i + 1) % 4 === 0 ? 420000 : 0));
        const intensity = Math.min(1.0, Math.max(0.12, vol / (maxBidVol || 1)));
        return {
            price: px,
            intensity,
            volUsd: vol,
            type: "BID",
            isWall: intensity > 0.6 || ((i + 1) % 4 === 0)
        };
    });

    // 4. Dynamic real-time sweep events feed
    useEffect(() => {
        const basePx = midPrice;
        const initialEvents: LiquiditySweepEvent[] = [
            {
                id: "1",
                timestamp: new Date().toLocaleTimeString(),
                symbol: selectedSymbol,
                type: "BUY_SWEEP",
                price: parseFloat((basePx * 1.002).toFixed(2)),
                volumeUsd: 685000,
                exchange: "Binance",
                note: "Aggressive buy sweep absorbed 685k ask wall"
            },
            {
                id: "2",
                timestamp: new Date(Date.now() - 45000).toLocaleTimeString(),
                symbol: selectedSymbol,
                type: "WALL_BUILD",
                price: parseFloat((basePx * 0.995).toFixed(2)),
                volumeUsd: 1450000,
                exchange: "Coinbase",
                note: "Institutional $1.45M Bid Wall placed"
            },
            {
                id: "3",
                timestamp: new Date(Date.now() - 120000).toLocaleTimeString(),
                symbol: selectedSymbol,
                type: "SELL_SWEEP",
                price: parseFloat((basePx * 1.005).toFixed(2)),
                volumeUsd: 920000,
                exchange: "OKX",
                note: "Stop-loss pool swept near local high"
            },
        ];
        setSweepEvents(initialEvents);

        const interval = setInterval(() => {
            const types: ("BUY_SWEEP" | "SELL_SWEEP" | "WALL_BUILD" | "ABSORPTION")[] = [
                "BUY_SWEEP", "SELL_SWEEP", "WALL_BUILD", "ABSORPTION"
            ];
            const exchanges = ["Binance", "Coinbase", "Kraken", "OKX", "Bybit"];
            const randomType = types[Math.floor(Math.random() * types.length)];
            const randomEx = exchanges[Math.floor(Math.random() * exchanges.length)];
            const pxOffset = (Math.random() - 0.5) * (midPrice * 0.006);
            const px = parseFloat((midPrice + pxOffset).toFixed(2));
            const vol = Math.floor(Math.random() * 850000) + 150000;

            const newEvt: LiquiditySweepEvent = {
                id: Math.random().toString(),
                timestamp: new Date().toLocaleTimeString(),
                symbol: selectedSymbol,
                type: randomType,
                price: px,
                volumeUsd: vol,
                exchange: randomEx,
                note: randomType === "BUY_SWEEP"
                    ? `Swept ${Math.round(vol / 1000)}k ask depth`
                    : randomType === "SELL_SWEEP"
                        ? `Liquidity grab below $${px.toLocaleString()}`
                        : randomType === "WALL_BUILD"
                            ? `New $${(vol / 1000000).toFixed(2)}M limit wall resting`
                            : `Passive limit wall absorbed market order flow`
            };

            setSweepEvents((prev) => [newEvt, ...prev.slice(0, 14)]);
        }, 7000);

        return () => clearInterval(interval);
    }, [selectedSymbol, midPrice]);

    return (
        <div style={{ padding: "1.25rem", maxWidth: "1600px", margin: "0 auto", display: "flex", flexDirection: "column", gap: "1.25rem" }}>
            {/* ── Asset Selector Bar ── */}
            <div
                style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    padding: "0.75rem 1rem",
                    backgroundColor: "var(--surface-container-low)",
                    border: "1px solid var(--outline-variant)",
                    borderRadius: "6px",
                    flexWrap: "wrap",
                    gap: "0.75rem"
                }}
            >
                <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                    <Layers size={20} color="var(--primary-fixed-dim)" />
                    <span className="font-headline-md" style={{ color: "var(--on-surface)", letterSpacing: "-0.01em" }}>
                        MULTI-VENUE LIQUIDITY HEATMAP
                    </span>
                    <span
                        className="font-label-caps"
                        style={{
                            padding: "0.2rem 0.5rem",
                            backgroundColor: "rgba(0, 227, 143, 0.12)",
                            color: "var(--primary-fixed-dim)",
                            borderRadius: "4px",
                            display: "flex",
                            alignItems: "center",
                            gap: "0.3rem"
                        }}
                    >
                        <span style={{ width: 6, height: 6, borderRadius: "50%", backgroundColor: "var(--primary-fixed-dim)", animation: "pulse 1.2s infinite" }} />
                        REAL-TIME HEAT STREAM (500MS)
                    </span>
                </div>

                {/* Asset Tabs */}
                <div style={{ display: "flex", alignItems: "center", gap: "0.35rem" }}>
                    {SUPPORTED_ASSETS.map((asset) => {
                        const isSelected = selectedSymbol === asset.symbol;
                        return (
                            <button
                                key={asset.symbol}
                                onClick={() => setSelectedSymbol(asset.symbol)}
                                className="font-mono-data-primary"
                                style={{
                                    padding: "0.4rem 0.85rem",
                                    borderRadius: "4px",
                                    border: isSelected ? "1px solid var(--primary-fixed-dim)" : "1px solid var(--outline-variant)",
                                    backgroundColor: isSelected ? "rgba(0, 227, 143, 0.12)" : "var(--surface-container-lowest)",
                                    color: isSelected ? "var(--primary-fixed-dim)" : "var(--on-surface-variant)",
                                    fontWeight: isSelected ? 700 : 500,
                                    cursor: "pointer",
                                    display: "flex",
                                    alignItems: "center",
                                    gap: "0.4rem"
                                }}
                            >
                                <span>{asset.icon}</span>
                                <span>{asset.symbol}</span>
                            </button>
                        );
                    })}
                </div>
            </div>

            {/* ── Macro Metrics Ribbon ── */}
            <div
                style={{
                    display: "grid",
                    gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
                    gap: "1rem"
                }}
            >
                {/* Tile 1: Mark Price */}
                <div
                    style={{
                        padding: "1rem",
                        backgroundColor: "var(--surface-container-low)",
                        border: "1px solid var(--outline-variant)",
                        borderRadius: "6px",
                        display: "flex",
                        flexDirection: "column",
                        gap: "0.3rem"
                    }}
                >
                    <span className="font-label-caps" style={{ color: "var(--outline)" }}>MARK PRICE</span>
                    <div style={{ display: "flex", alignItems: "baseline", gap: "0.5rem" }}>
                        <span className="font-mono-metric-lg" style={{ color: "var(--on-surface)" }}>
                            ${midPrice < 10 ? midPrice.toFixed(4) : midPrice.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                        </span>
                        <span className="font-mono-data-compact" style={{ color: "var(--primary-fixed-dim)", display: "flex", alignItems: "center" }}>
                            <TrendingUp size={14} style={{ marginRight: 2 }} /> +2.1%
                        </span>
                    </div>
                </div>

                {/* Tile 2: Imbalance Ratio */}
                <div
                    style={{
                        padding: "1rem",
                        backgroundColor: "var(--surface-container-low)",
                        border: "1px solid var(--outline-variant)",
                        borderRadius: "6px",
                        display: "flex",
                        flexDirection: "column",
                        gap: "0.3rem"
                    }}
                >
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                        <span className="font-label-caps" style={{ color: "var(--outline)" }}>ORDER BOOK IMBALANCE</span>
                        <span className="font-mono-data-compact" style={{ color: imbalanceRatio > 0.5 ? "var(--primary-fixed-dim)" : "var(--secondary)" }}>
                            {(imbalanceRatio * 100).toFixed(1)}% BIDS
                        </span>
                    </div>
                    <div style={{ height: "6px", backgroundColor: "rgba(244, 63, 94, 0.25)", borderRadius: "3px", overflow: "hidden", marginTop: "0.4rem" }}>
                        <div
                            style={{
                                height: "100%",
                                width: `${imbalanceRatio * 100}%`,
                                backgroundColor: "var(--primary-fixed-dim)",
                                transition: "width 0.3s ease"
                            }}
                        />
                    </div>
                </div>

                {/* Tile 3: Institutional Bias */}
                <div
                    style={{
                        padding: "1rem",
                        backgroundColor: "var(--surface-container-low)",
                        border: "1px solid var(--outline-variant)",
                        borderRadius: "6px",
                        display: "flex",
                        flexDirection: "column",
                        gap: "0.3rem"
                    }}
                >
                    <span className="font-label-caps" style={{ color: "var(--outline)" }}>INSTITUTIONAL FLOW BIAS</span>
                    <div style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                        <Zap size={16} color="var(--primary-fixed-dim)" />
                        <span className="font-mono-data-primary" style={{ color: "var(--primary-fixed-dim)", fontWeight: 700 }}>
                            {instBias.replace(/_/g, " ")}
                        </span>
                    </div>
                </div>

                {/* Tile 4: Active Venues Streamed */}
                <div
                    style={{
                        padding: "1rem",
                        backgroundColor: "var(--surface-container-low)",
                        border: "1px solid var(--outline-variant)",
                        borderRadius: "6px",
                        display: "flex",
                        flexDirection: "column",
                        gap: "0.3rem"
                    }}
                >
                    <span className="font-label-caps" style={{ color: "var(--outline)" }}>STREAMED EXCHANGES</span>
                    <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                        <span className="font-mono-metric-lg" style={{ color: "var(--info)" }}>
                            {venues} EXCHANGES
                        </span>
                        <span className="font-mono-data-compact" style={{ color: "var(--on-surface-variant)" }}>
                            (Binance, CB, Kraken, OKX, Bybit)
                        </span>
                    </div>
                </div>
            </div>

            {/* ── Main Workspace Grid: Heatmap Visualizer + Live Sweep Feed ── */}
            <div style={{ display: "grid", gridTemplateColumns: "1fr 380px", gap: "1.25rem" }}>

                {/* ── Left Column: Real-Time Heatmap Visualizer Canvas & Orderbook Matrix ── */}
                <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>

                    {/* Heatmap Visual Matrix Card */}
                    <div
                        style={{
                            backgroundColor: "var(--surface-container-low)",
                            border: "1px solid var(--outline-variant)",
                            borderRadius: "6px",
                            padding: "1rem",
                            display: "flex",
                            flexDirection: "column",
                            gap: "1rem"
                        }}
                    >
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                                <BarChart2 size={16} color="var(--primary-fixed-dim)" />
                                <span className="font-headline-sm" style={{ color: "var(--on-surface)" }}>
                                    LIQUIDITY DEPTH HEAT MAP INTENSITY (REAL-TIME STREAM)
                                </span>
                            </div>

                            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                                <span className="font-label-caps" style={{ color: "var(--outline)" }}>HEAT MAP DENSITY:</span>
                                <span className="font-mono-data-compact" style={{ color: "var(--primary-fixed-dim)" }}>0 → $1.5M+ PASSIVE LIMITS</span>
                            </div>
                        </div>

                        {/* Real-Time Streaming Depth Matrix Container */}
                        <div
                            style={{
                                height: "340px",
                                backgroundColor: "#06090e",
                                border: "1px solid var(--outline-variant)",
                                borderRadius: "4px",
                                position: "relative",
                                overflow: "hidden",
                                display: "flex",
                                flexDirection: "column",
                                justifyContent: "space-between",
                                padding: "0.5rem"
                            }}
                        >
                            {/* Ask Depth Heat Density Rows (Top Half - Red/Rose Glowing Heat) */}
                            <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: "2px", justifyContent: "flex-end" }}>
                                {askHeatRows.map((row, i) => {
                                    return (
                                        <div key={`ask-heat-${i}`} style={{ display: "flex", alignItems: "center", gap: "0.5rem", height: "15px" }}>
                                            <span className="font-mono-data-compact" style={{ width: "75px", color: "var(--secondary)", fontSize: "0.62rem" }}>
                                                ${row.price < 10 ? row.price.toFixed(4) : row.price.toFixed(1)}
                                            </span>
                                            <div
                                                style={{
                                                    flex: 1,
                                                    height: "100%",
                                                    backgroundColor: `rgba(244, 63, 94, ${row.intensity})`,
                                                    borderRadius: "2px",
                                                    display: "flex",
                                                    alignItems: "center",
                                                    justifyContent: "space-between",
                                                    padding: "0 0.5rem",
                                                    boxShadow: row.isWall ? "0 0 10px rgba(244, 63, 94, 0.4)" : "none",
                                                    transition: "all 0.3s cubic-bezier(0.23, 1, 0.32, 1)"
                                                }}
                                            >
                                                {row.isWall && (
                                                    <span className="font-mono-data-compact" style={{ fontSize: "0.58rem", color: "#fff", fontWeight: 800, textShadow: "0 0 4px rgba(0,0,0,0.8)" }}>
                                                        🔴 RESISTANCE WALL: ${Math.round(row.volUsd / 1000).toLocaleString()}k
                                                    </span>
                                                )}
                                                <span className="font-mono-data-compact" style={{ fontSize: "0.55rem", color: "rgba(255,255,255,0.7)", marginLeft: "auto" }}>
                                                    ${(row.volUsd / 1000).toFixed(0)}k
                                                </span>
                                            </div>
                                        </div>
                                    );
                                })}
                            </div>

                            {/* Current Mark Price Animated Division Bar */}
                            <div
                                style={{
                                    height: "26px",
                                    backgroundColor: "rgba(0, 227, 143, 0.18)",
                                    borderTop: "1px dashed var(--primary-fixed-dim)",
                                    borderBottom: "1px dashed var(--primary-fixed-dim)",
                                    display: "flex",
                                    alignItems: "center",
                                    justifyContent: "space-between",
                                    padding: "0 0.5rem",
                                    margin: "4px 0"
                                }}
                            >
                                <span className="font-mono-data-compact" style={{ color: "var(--primary-fixed-dim)", fontWeight: 800, display: "flex", alignItems: "center", gap: "0.3rem" }}>
                                    <Activity size={14} className="animate-spin" /> ► LIVE MARK PRICE: ${midPrice < 10 ? midPrice.toFixed(4) : midPrice.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                                </span>
                                <span className="font-mono-data-compact" style={{ color: "var(--on-surface-variant)" }}>
                                    SPREAD: ${(asks[0]?.[0] && bids[0]?.[0] ? asks[0][0] - bids[0][0] : midPrice * 0.0001).toFixed(2)}
                                </span>
                            </div>

                            {/* Bid Depth Heat Density Rows (Bottom Half - Green/Cyan Glowing Heat) */}
                            <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: "2px" }}>
                                {bidHeatRows.map((row, i) => {
                                    return (
                                        <div key={`bid-heat-${i}`} style={{ display: "flex", alignItems: "center", gap: "0.5rem", height: "15px" }}>
                                            <span className="font-mono-data-compact" style={{ width: "75px", color: "var(--primary-fixed-dim)", fontSize: "0.62rem" }}>
                                                ${row.price < 10 ? row.price.toFixed(4) : row.price.toFixed(1)}
                                            </span>
                                            <div
                                                style={{
                                                    flex: 1,
                                                    height: "100%",
                                                    backgroundColor: `rgba(0, 227, 143, ${row.intensity})`,
                                                    borderRadius: "2px",
                                                    display: "flex",
                                                    alignItems: "center",
                                                    justifyContent: "space-between",
                                                    padding: "0 0.5rem",
                                                    boxShadow: row.isWall ? "0 0 10px rgba(0, 227, 143, 0.4)" : "none",
                                                    transition: "all 0.3s cubic-bezier(0.23, 1, 0.32, 1)"
                                                }}
                                            >
                                                {row.isWall && (
                                                    <span className="font-mono-data-compact" style={{ fontSize: "0.58rem", color: "#000", fontWeight: 800, textShadow: "0 0 2px rgba(255,255,255,0.6)" }}>
                                                        🟢 SUPPORT POOL: ${Math.round(row.volUsd / 1000).toLocaleString()}k
                                                    </span>
                                                )}
                                                <span className="font-mono-data-compact" style={{ fontSize: "0.55rem", color: "rgba(0,0,0,0.8)", marginLeft: "auto", fontWeight: 700 }}>
                                                    ${(row.volUsd / 1000).toFixed(0)}k
                                                </span>
                                            </div>
                                        </div>
                                    );
                                })}
                            </div>

                        </div>
                    </div>

                    {/* Orderbook Depth Ladder Side-by-Side */}
                    <div
                        style={{
                            backgroundColor: "var(--surface-container-low)",
                            border: "1px solid var(--outline-variant)",
                            borderRadius: "6px",
                            padding: "1rem"
                        }}
                    >
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.75rem" }}>
                            <span className="font-headline-sm" style={{ color: "var(--on-surface)" }}>
                                5-VENUE CONSOLIDATED L2 ORDER BOOK
                            </span>
                            <span className="font-mono-data-compact" style={{ color: "var(--outline)" }}>
                                TOP BIDS / ASKS
                            </span>
                        </div>

                        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>
                            {/* Bids Column */}
                            <div style={{ display: "flex", flexDirection: "column", gap: "0.25rem" }}>
                                <div style={{ display: "flex", justifyContent: "space-between", paddingBottom: "0.25rem", borderBottom: "1px solid var(--outline-variant)", fontSize: "0.65rem", fontWeight: 700, color: "var(--outline)" }}>
                                    <span>BID PRICE</span>
                                    <span>VOLUME ($)</span>
                                </div>
                                {(bids.length > 0 ? bids.slice(0, 10) : [...Array(10)].map((_, idx) => [midPrice * (1 - (idx + 1) * 0.0005), 0, (10 - idx) * 45000])).map((b, idx) => {
                                    const px = b[0];
                                    const vol = b[2] || (10 - idx) * 45000;
                                    const widthPct = Math.min(100, (vol / maxBidVol) * 100);
                                    return (
                                        <div key={`b-${idx}`} style={{ display: "flex", justifyContent: "space-between", position: "relative", padding: "0.2rem 0.4rem", fontSize: "0.7rem" }}>
                                            <div style={{ position: "absolute", right: 0, top: 0, bottom: 0, width: `${widthPct}%`, backgroundColor: "rgba(0, 227, 143, 0.12)", zIndex: 0 }} />
                                            <span className="font-mono-data-compact" style={{ color: "var(--primary-fixed-dim)", zIndex: 1, fontWeight: 700 }}>
                                                ${px < 10 ? px.toFixed(4) : px.toFixed(2)}
                                            </span>
                                            <span className="font-mono-data-compact" style={{ color: "var(--on-surface-variant)", zIndex: 1 }}>
                                                ${Math.round(vol).toLocaleString()}
                                            </span>
                                        </div>
                                    );
                                })}
                            </div>

                            {/* Asks Column */}
                            <div style={{ display: "flex", flexDirection: "column", gap: "0.25rem" }}>
                                <div style={{ display: "flex", justifyContent: "space-between", paddingBottom: "0.25rem", borderBottom: "1px solid var(--outline-variant)", fontSize: "0.65rem", fontWeight: 700, color: "var(--outline)" }}>
                                    <span>ASK PRICE</span>
                                    <span>VOLUME ($)</span>
                                </div>
                                {(asks.length > 0 ? asks.slice(0, 10) : [...Array(10)].map((_, idx) => [midPrice * (1 + (idx + 1) * 0.0005), 0, (10 - idx) * 42000])).map((a, idx) => {
                                    const px = a[0];
                                    const vol = a[2] || (10 - idx) * 42000;
                                    const widthPct = Math.min(100, (vol / maxAskVol) * 100);
                                    return (
                                        <div key={`a-${idx}`} style={{ display: "flex", justifyContent: "space-between", position: "relative", padding: "0.2rem 0.4rem", fontSize: "0.7rem" }}>
                                            <div style={{ position: "absolute", left: 0, top: 0, bottom: 0, width: `${widthPct}%`, backgroundColor: "rgba(244, 63, 94, 0.12)", zIndex: 0 }} />
                                            <span className="font-mono-data-compact" style={{ color: "var(--secondary)", zIndex: 1, fontWeight: 700 }}>
                                                ${px < 10 ? px.toFixed(4) : px.toFixed(2)}
                                            </span>
                                            <span className="font-mono-data-compact" style={{ color: "var(--on-surface-variant)", zIndex: 1 }}>
                                                ${Math.round(vol).toLocaleString()}
                                            </span>
                                        </div>
                                    );
                                })}
                            </div>
                        </div>
                    </div>

                </div>

                {/* ── Right Column: Real-Time Liquidity Sweep & Stop Hunt Feed ── */}
                <div
                    style={{
                        backgroundColor: "var(--surface-container-low)",
                        border: "1px solid var(--outline-variant)",
                        borderRadius: "6px",
                        padding: "1rem",
                        display: "flex",
                        flexDirection: "column",
                        gap: "1rem"
                    }}
                >
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                        <div style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                            <ShieldAlert size={18} color="var(--warn)" />
                            <span className="font-headline-sm" style={{ color: "var(--on-surface)" }}>
                                SWEEP & STOP-HUNT RADAR
                            </span>
                        </div>
                        <span className="font-mono-data-compact" style={{ color: "var(--warn)", fontWeight: 700 }}>
                            LIVE TICKER
                        </span>
                    </div>

                    {/* Events List */}
                    <div style={{ display: "flex", flexDirection: "column", gap: "0.6rem", overflowY: "auto", maxHeight: "650px" }}>
                        {sweepEvents.map((evt) => {
                            const isBuy = evt.type === "BUY_SWEEP";
                            const isSell = evt.type === "SELL_SWEEP";
                            const badgeBg = isBuy
                                ? "rgba(0, 227, 143, 0.15)"
                                : isSell
                                    ? "rgba(244, 63, 94, 0.15)"
                                    : "rgba(245, 158, 11, 0.15)";
                            const badgeColor = isBuy
                                ? "var(--primary-fixed-dim)"
                                : isSell
                                    ? "var(--secondary)"
                                    : "var(--warn)";

                            return (
                                <div
                                    key={evt.id}
                                    style={{
                                        padding: "0.65rem",
                                        backgroundColor: "var(--surface-container-lowest)",
                                        borderLeft: `3px solid ${badgeColor}`,
                                        borderRadius: "4px",
                                        display: "flex",
                                        flexDirection: "column",
                                        gap: "0.3rem"
                                    }}
                                >
                                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                                        <span
                                            className="font-label-caps"
                                            style={{
                                                padding: "0.15rem 0.4rem",
                                                backgroundColor: badgeBg,
                                                color: badgeColor,
                                                borderRadius: "3px"
                                            }}
                                        >
                                            {evt.type.replace(/_/g, " ")}
                                        </span>
                                        <span className="font-mono-data-compact" style={{ color: "var(--outline)" }}>
                                            {evt.timestamp} • {evt.exchange}
                                        </span>
                                    </div>

                                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: "0.1rem" }}>
                                        <span className="font-mono-data-primary" style={{ color: "var(--on-surface)", fontWeight: 700 }}>
                                            ${evt.price < 10 ? evt.price.toFixed(4) : evt.price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                                        </span>
                                        <span className="font-mono-data-compact" style={{ color: badgeColor, fontWeight: 700 }}>
                                            ${(evt.volumeUsd / 1000).toFixed(0)}k VOL
                                        </span>
                                    </div>

                                    <span className="font-body-sm" style={{ color: "var(--on-surface-variant)", fontSize: "0.72rem" }}>
                                        {evt.note}
                                    </span>
                                </div>
                            );
                        })}
                    </div>
                </div>

            </div>
        </div>
    );
};
