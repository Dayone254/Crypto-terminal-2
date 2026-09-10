"use client";

import React, { useEffect, useState } from "react";
import { ArrowDownAZ, ArrowUpZA, ShieldAlert } from "lucide-react";
import { wsBase } from "@/lib/api";

interface L2Data {
    bids: [number, number, number][]; // price, qty, vol_usd
    asks: [number, number, number][];
    metrics: {
        total_bid_vol_usd: number;
        total_ask_vol_usd: number;
        imbalance_ratio: number;
        buy_walls: { price: number; vol_usd: number }[];
        sell_walls: { price: number; vol_usd: number }[];
    };
}

export function Level2Depth({ symbol }: { symbol: string }) {
    const [l2Data, setL2Data] = useState<L2Data | null>(null);
    const [connectionStatus, setConnectionStatus] = useState<"CONNECTING" | "CONNECTED" | "DISCONNECTED">("CONNECTING");

    useEffect(() => {
        let ws: WebSocket;
        let reconnectTimeout: NodeJS.Timeout;
        let disposed = false;

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
                const data = JSON.parse(event.data);
                setL2Data(data);
            };

            ws.onclose = () => {
                if (disposed) return;
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
                // Prevent strict mode "closed before established" console spam 
                // by optionally silencing it or just keeping it clean.
                ws.close();
            }
        };
    }, [symbol]);

    const renderLevel = (price: number, volUsd: number, type: "BID" | "ASK", maxVol: number) => {
        const fillWidth = Math.min((volUsd / (maxVol || 1)) * 100, 100);
        const isBid = type === "BID";
        const color = isBid ? "#10B981" : "#F43F5E";
        const bgFill = isBid ? "rgba(16, 185, 129, 0.15)" : "rgba(244, 63, 94, 0.15)";

        return (
            <div
                key={price}
                style={{
                    display: "flex",
                    justifyContent: "space-between",
                    padding: "0.2rem 0.5rem",
                    position: "relative",
                    fontSize: "0.7rem",
                    overflow: "hidden",
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
                <span className="mono" style={{ position: "relative", zIndex: 1, color: "var(--text-muted)" }}>
                    ${Math.round(volUsd).toLocaleString()}
                </span>
            </div>
        );
    };

    if (!l2Data) {
        return (
            <div style={{ background: "#0B0F19", border: "none", borderRadius: 0, padding: "1.5rem", textAlign: "center", color: "var(--text-dim)", fontSize: "0.75rem" }}>
                Connecting to L2 Liquidity Engine...
            </div>
        );
    }

    const maxAskVol = Math.max(...l2Data.asks.slice(0, 10).map((a) => a[2]), 1000);
    const maxBidVol = Math.max(...l2Data.bids.slice(0, 10).map((b) => b[2]), 1000);
    const ratio = l2Data.metrics.imbalance_ratio;

    return (
        <div style={{ background: "#0B0F19", border: "none", borderRadius: 0, padding: "1rem", display: "flex", flexDirection: "column", gap: "1rem" }}>

            {/* Header & Imbalance Gauge */}
            <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                    <h3 style={{ fontSize: "0.85rem", fontWeight: 800, color: "#FFF", display: "flex", alignItems: "center", gap: "0.4rem" }}>
                        L2 ORDERBOOK DEPTH
                    </h3>
                    <div style={{ display: "flex", alignItems: "center", gap: "0.4rem", fontSize: "0.6rem", fontWeight: 800 }}>
                        <span style={{ width: 6, height: 6, borderRadius: "50%", background: connectionStatus === "CONNECTED" ? "#10B981" : "#F59E0B" }} />
                        <span style={{ color: "var(--text-dim)" }}>MULTIPLEXED L2 (CB+BINANCE)</span>
                    </div>
                </div>

                {/* Imbalance Ratio Bar */}
                <div style={{ display: "flex", flexDirection: "column", gap: "0.2rem" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.65rem", fontWeight: 800 }}>
                        <span style={{ color: "#10B981" }}>BIDS {(ratio * 100).toFixed(1)}%</span>
                        <span style={{ color: "#F43F5E" }}>ASKS {((1 - ratio) * 100).toFixed(1)}%</span>
                    </div>
                    <div style={{ height: "4px", background: "rgba(244, 63, 94, 0.3)", borderRadius: 0, overflow: "hidden", display: "flex" }}>
                        <div style={{ height: "100%", width: `${ratio * 100}%`, background: "#10B981", transition: "width 0.2s ease" }} />
                    </div>
                </div>
            </div>

            {/* Walls Detection Feed */}
            {l2Data.metrics.buy_walls.length > 0 || l2Data.metrics.sell_walls.length > 0 ? (
                <div style={{ display: "flex", flexDirection: "column", gap: "0.4rem" }}>
                    {l2Data.metrics.sell_walls.slice(0, 2).map((w, i) => (
                        <div key={`sw-${i}`} style={{ background: "rgba(244, 63, 94, 0.1)", border: "none", padding: "0.3rem 0.5rem", borderRadius: 0, display: "flex", alignItems: "center", gap: "0.3rem", fontSize: "0.65rem", fontWeight: 800, color: "#F43F5E" }}>
                            <ArrowDownAZ size={12} />
                            WALL: ${Math.round(w.vol_usd).toLocaleString()} @ {w.price < 1 ? w.price.toFixed(5) : w.price.toFixed(2)}
                        </div>
                    ))}
                    {l2Data.metrics.buy_walls.slice(0, 2).map((w, i) => (
                        <div key={`bw-${i}`} style={{ background: "rgba(16, 185, 129, 0.1)", border: "none", padding: "0.3rem 0.5rem", borderRadius: 0, display: "flex", alignItems: "center", gap: "0.3rem", fontSize: "0.65rem", fontWeight: 800, color: "#10B981" }}>
                            <ArrowUpZA size={12} />
                            WALL: ${Math.round(w.vol_usd).toLocaleString()} @ {w.price < 1 ? w.price.toFixed(5) : w.price.toFixed(2)}
                        </div>
                    ))}
                </div>
            ) : null}

            {/* Depth Ladder */}
            <div style={{ display: "flex", gap: "0.5rem" }}>
                {/* Bids */}
                <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: "2px" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.6rem", color: "var(--text-dim)", fontWeight: 700, paddingBottom: "0.2rem", borderBottom: "none" }}>
                        <span>BID</span>
                        <span>$ VOL</span>
                    </div>
                    {l2Data.bids.slice(0, 10).map((b) => renderLevel(b[0], b[2], "BID", maxBidVol))}
                </div>

                {/* Asks */}
                <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: "2px" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.6rem", color: "var(--text-dim)", fontWeight: 700, paddingBottom: "0.2rem", borderBottom: "none" }}>
                        <span>ASK</span>
                        <span>$ VOL</span>
                    </div>
                    {l2Data.asks.slice(0, 10).map((a) => renderLevel(a[0], a[2], "ASK", maxAskVol))}
                </div>
            </div>

        </div>
    );
}
