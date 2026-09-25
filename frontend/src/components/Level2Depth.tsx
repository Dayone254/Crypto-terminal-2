"use client";

import React, { useEffect, useState } from "react";
import { ArrowDownAZ, ArrowUpZA, ShieldCheck, Zap } from "lucide-react";
import { wsBase } from "@/lib/api";
import { L2Data, isDisabledFrame, isL2Payload } from "@/lib/l2";

type ConnectionState = "CONNECTING" | "CONNECTED" | "DISCONNECTED" | "UNAVAILABLE";

export function Level2Depth({ symbol }: { symbol: string }) {
    const [l2Data, setL2Data] = useState<L2Data | null>(null);
    const [connectionStatus, setConnectionStatus] = useState<ConnectionState>("CONNECTING");

    useEffect(() => {
        let ws: WebSocket;
        let reconnectTimeout: NodeJS.Timeout;
        let disposed = false;
        let disabled = false;

        const connect = () => {
            setConnectionStatus("CONNECTING");
            ws = new WebSocket(`${wsBase()}/api/v1/ws/l2/${symbol}`);

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
                setConnectionStatus("DISCONNECTED");
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
    }, [symbol]);

    const renderLevel = (price: number, volUsd: number, type: "BID" | "ASK", maxVol: number, idx: number) => {
        const fillWidth = Math.min((volUsd / (maxVol || 1)) * 100, 100);
        const isBid = type === "BID";
        const isEven = idx % 2 === 0;

        let color = "var(--text-main)";
        if (fillWidth > 70) color = isBid ? "var(--pos-bright)" : "var(--neg-bright)";
        else if (fillWidth > 30) color = isBid ? "var(--pos)" : "var(--neg)";

        const bgFill = isBid ? "rgba(16, 185, 129, 0.12)" : "rgba(244, 63, 94, 0.12)";
        const rowBg = isEven ? "rgba(255,255,255,0.015)" : "transparent";

        return (
            <div
                key={`${type}-${price}`}
                style={{
                    display: "flex",
                    justifyContent: "space-between",
                    padding: "0.1rem 0.25rem",
                    position: "relative",
                    fontSize: "0.68rem",
                    overflow: "hidden",
                    background: rowBg
                }}
            >
                <div
                    style={{
                        position: "absolute",
                        top: 0,
                        right: isBid ? 0 : "auto",
                        left: isBid ? "auto" : 0,
                        height: "100%",
                        width: `${fillWidth}%`,
                        background: bgFill,
                        zIndex: 0,
                        transition: "width 0.1s linear"
                    }}
                />
                <span className="mono" style={{ position: "relative", zIndex: 1, color, fontWeight: 700 }}>
                    {price < 1 ? price.toFixed(5) : price.toFixed(2)}
                </span>
                <span className="mono" style={{ position: "relative", zIndex: 1, color: "var(--text-3)", fontSize: "0.65rem" }}>
                    {Math.round(volUsd).toLocaleString()}
                </span>
            </div>
        );
    };

    const placeholder = (text: string, hint?: string) => (
        <div
            style={{
                background: "var(--surface-1)",
                border: "none",
                borderRadius: 0,
                padding: "1.5rem",
                textAlign: "center",
                color: "var(--text-dim)",
                fontSize: "0.72rem",
                lineHeight: 1.5,
            }}
        >
            {text}
            {hint && (
                <div className="mono" style={{ marginTop: "0.35rem", fontSize: "0.62rem", color: "var(--text-dim)" }}>
                    {hint}
                </div>
            )}
        </div>
    );

    if (connectionStatus === "UNAVAILABLE") {
        return placeholder("Live order book unavailable.", "Enable ENABLE_LIVE_WS on the backend to stream depth.");
    }

    if (!isL2Payload(l2Data)) {
        return placeholder("Connecting to Multi-Exchange L2 Engine...");
    }

    const bids = l2Data.bids;
    const asks = l2Data.asks;
    const buyWalls = l2Data.metrics.buy_walls ?? [];
    const sellWalls = l2Data.metrics.sell_walls ?? [];
    const ratio = typeof l2Data.metrics.imbalance_ratio === "number" ? l2Data.metrics.imbalance_ratio : 0.5;
    const supportLevels = l2Data.metrics.support_levels ?? [];
    const resistanceLevels = l2Data.metrics.resistance_levels ?? [];
    const bias = l2Data.metrics.institutional_bias ?? "NEUTRAL";
    const venues = l2Data.metrics.total_venues ?? 0;

    const maxAskVol = Math.max(...asks.slice(0, 10).map((a) => a[2]), 1000);
    const maxBidVol = Math.max(...bids.slice(0, 10).map((b) => b[2]), 1000);

    return (
        <div className="panel" style={{ padding: "var(--sp-4)", display: "flex", flexDirection: "column", gap: "var(--sp-4)" }}>

            {/* Header & Imbalance Gauge */}
            <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                    <h3 style={{ fontSize: "0.85rem", fontWeight: 800, color: "var(--text-strong)", display: "flex", alignItems: "center", gap: "0.4rem" }}>
                        MULTI-VENUE L2 DEPTH
                    </h3>
                    <div style={{ display: "flex", alignItems: "center", gap: "0.4rem", fontSize: "0.6rem", fontWeight: 800 }}>
                        <span style={{ width: 6, height: 6, borderRadius: "50%", background: connectionStatus === "CONNECTED" ? "var(--pos)" : "var(--warn)" }} />
                        <span style={{ color: "var(--text-dim)" }}>{venues} VENUES (CB+BINANCE+KRAKEN+OKX+BYBIT)</span>
                    </div>
                </div>

                {/* Institutional Bias Tag */}
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", fontSize: "0.65rem", fontWeight: 800 }}>
                    <span style={{ color: "var(--text-dim)", display: "flex", alignItems: "center", gap: "0.2rem" }}>
                        <Zap size={12} className="text-amber-400" /> INST. FLOW:
                    </span>
                    <span className="mono" style={{ color: bias.includes("BULLISH") ? "var(--pos)" : bias.includes("BEARISH") ? "var(--neg)" : "var(--text-dim)" }}>
                        {bias.replace(/_/g, " ")}
                    </span>
                </div>

                {/* Imbalance Ratio Bar */}
                <div style={{ display: "flex", flexDirection: "column", gap: "0.2rem" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.65rem", fontWeight: 800 }}>
                        <span style={{ color: "var(--pos)" }}>BIDS {(ratio * 100).toFixed(1)}%</span>
                        <span style={{ color: "var(--neg)" }}>ASKS {((1 - ratio) * 100).toFixed(1)}%</span>
                    </div>
                    <div style={{ height: "4px", background: "rgba(244, 63, 94, 0.3)", borderRadius: 0, overflow: "hidden", display: "flex" }}>
                        <div style={{ height: "100%", width: `${ratio * 100}%`, background: "var(--pos)", transition: "width 0.2s ease" }} />
                    </div>
                </div>
            </div>

            {/* Key Support & Resistance Levels */}
            {(supportLevels.length > 0 || resistanceLevels.length > 0) && (
                <div style={{ display: "flex", flexDirection: "column", gap: "0.3rem", background: "rgba(255,255,255,0.02)", padding: "0.4rem", borderRadius: 4, border: "1px solid rgba(255,255,255,0.05)" }}>
                    <div style={{ fontSize: "0.6rem", fontWeight: 800, color: "var(--text-dim)", display: "flex", alignItems: "center", gap: "0.3rem" }}>
                        <ShieldCheck size={12} /> MULTI-VENUE KEY LIQUIDITY LEVELS
                    </div>
                    {supportLevels.slice(0, 1).map((s, i) => (
                        <div key={`sup-${i}`} style={{ display: "flex", justifyContent: "space-between", fontSize: "0.65rem", color: "var(--pos)", fontWeight: 700 }}>
                            <span>SUP WALL: ${s.price < 1 ? s.price.toFixed(5) : s.price.toFixed(2)}</span>
                            <span>{s.strength}x AVG DEPTH</span>
                        </div>
                    ))}
                    {resistanceLevels.slice(0, 1).map((r, i) => (
                        <div key={`res-${i}`} style={{ display: "flex", justifyContent: "space-between", fontSize: "0.65rem", color: "var(--neg)", fontWeight: 700 }}>
                            <span>RES WALL: ${r.price < 1 ? r.price.toFixed(5) : r.price.toFixed(2)}</span>
                            <span>{r.strength}x AVG DEPTH</span>
                        </div>
                    ))}
                </div>
            )}

            {/* Walls Detection Feed */}
            {sellWalls.length > 0 || buyWalls.length > 0 ? (
                <div style={{ display: "flex", flexDirection: "column", gap: "0.4rem" }}>
                    {sellWalls.slice(0, 2).map((w, i) => (
                        <div key={`sw-${i}`} style={{ background: "rgba(244, 63, 94, 0.1)", border: "none", padding: "0.3rem 0.5rem", borderRadius: 0, display: "flex", alignItems: "center", gap: "0.3rem", fontSize: "0.65rem", fontWeight: 800, color: "var(--neg)" }}>
                            <ArrowDownAZ size={12} />
                            SELL WALL: ${Math.round(w.vol_usd).toLocaleString()} @ {w.price < 1 ? w.price.toFixed(5) : w.price.toFixed(2)}
                        </div>
                    ))}
                    {buyWalls.slice(0, 2).map((w, i) => (
                        <div key={`bw-${i}`} style={{ background: "rgba(16, 185, 129, 0.1)", border: "none", padding: "0.3rem 0.5rem", borderRadius: 0, display: "flex", alignItems: "center", gap: "0.3rem", fontSize: "0.65rem", fontWeight: 800, color: "var(--pos)" }}>
                            <ArrowUpZA size={12} />
                            BUY WALL: ${Math.round(w.vol_usd).toLocaleString()} @ {w.price < 1 ? w.price.toFixed(5) : w.price.toFixed(2)}
                        </div>
                    ))}
                </div>
            ) : null}

            {/* Depth Ladder */}
            <div style={{ display: "flex", gap: "0.5rem" }}>
                {/* Bids */}
                <div style={{ flex: 1, display: "flex", flexDirection: "column" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.6rem", color: "var(--text-dim)", fontWeight: 700, paddingBottom: "0.2rem", borderBottom: "1px solid var(--line)" }}>
                        <span>BID</span>
                        <span>$ VOL</span>
                    </div>
                    {bids.slice(0, 10).map((b, i) => renderLevel(b[0], b[2], "BID", maxBidVol, i))}
                </div>

                {/* Asks */}
                <div style={{ flex: 1, display: "flex", flexDirection: "column" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.6rem", color: "var(--text-dim)", fontWeight: 700, paddingBottom: "0.2rem", borderBottom: "1px solid var(--line)" }}>
                        <span>ASK</span>
                        <span>$ VOL</span>
                    </div>
                    {asks.slice(0, 10).map((a, i) => renderLevel(a[0], a[2], "ASK", maxAskVol, i))}
                </div>
            </div>

        </div>
    );
}
