"use client";

import React, { useEffect, useState, useRef } from "react";

export interface OrderbookPanelProps {
    productId: string;
}

const wsBase = () => {
    if (typeof window === "undefined") return "";
    return window.location.protocol === "https:" ? `wss://${window.location.host}` : `ws://${window.location.hostname}:8000`;
};

export const OrderbookPanel: React.FC<OrderbookPanelProps> = ({ productId }) => {
    const [bids, setBids] = useState<[number, number][]>([]);
    const [asks, setAsks] = useState<[number, number][]>([]);

    useEffect(() => {
        let wsL2: WebSocket | null = null;
        let disposed = false;
        let lastRender = 0;

        const connect = () => {
            const url = `${wsBase()}/api/v1/ws/l2/${productId}`;
            wsL2 = new WebSocket(url);

            wsL2.onmessage = (e) => {
                if (disposed) return;
                const now = Date.now();
                if (now - lastRender < 300) return; // limit to ~3fps for smooth human readability

                try {
                    const frame = JSON.parse(e.data);
                    if (!frame || !frame.asks || !frame.bids) return;

                    lastRender = now;
                    // Keep top 20 levels
                    const parsedAsks = frame.asks.slice(0, 20).map((a: any) => [Number(a[0]), Number(a[2] || a[1])]);
                    const parsedBids = frame.bids.slice(0, 20).map((b: any) => [Number(b[0]), Number(b[2] || b[1])]);

                    setAsks(parsedAsks);
                    setBids(parsedBids);
                } catch (err) { }
            };

            wsL2.onclose = () => {
                if (!disposed) setTimeout(connect, 3000);
            };
        };

        connect();
        return () => {
            disposed = true;
            if (wsL2) wsL2.close();
        };
    }, [productId]);

    const formatPrice = (v: number) => {
        if (v < 1) return v.toFixed(4);
        if (v < 10) return v.toFixed(3);
        if (v < 100) return v.toFixed(2);
        return v.toFixed(1);
    };

    const formatVol = (v: number) => {
        if (v >= 1000) return (v / 1000).toFixed(1) + "k";
        return v.toFixed(0);
    };

    // Calculate dynamic scaling for volume density bars
    const maxVol = Math.max(...bids.map(b => b[1]), ...asks.map(a => a[1]), 0.001);

    return (
        <div style={{
            display: "flex", flexDirection: "column", height: "100%",
            background: "rgba(15, 23, 42, 0.4)",
            borderLeft: "1px solid rgba(255, 255, 255, 0.05)",
            fontFamily: "var(--font-jetbrains)",
            fontSize: "0.65rem", overflow: "hidden"
        }}>
            <div style={{
                padding: "0.4rem 0.6rem", borderBottom: "1px solid rgba(255, 255, 255, 0.05)",
                color: "var(--text-4)", fontWeight: 800, fontSize: "0.55rem", letterSpacing: "0.05em",
                display: "flex", justifyContent: "space-between"
            }}>
                <span>PRICE</span>
                <span>SIZE</span>
            </div>

            <div style={{ flex: 1, display: "flex", flexDirection: "column", overflowY: "auto", overflowX: "hidden" }}>
                {/* Asks (Sell Side) - Reverse so lowest ask is at bottom of ask section */}
                <div style={{ display: "flex", flexDirection: "column-reverse", flex: 1, justifyContent: "flex-end" }}>
                    {asks.map((ask, idx) => {
                        const pct = Math.min(100, (ask[1] / maxVol) * 100);
                        return (
                            <div key={`ask-${ask[0]}-${idx}`} style={{
                                display: "flex", justifyContent: "space-between", position: "relative",
                                padding: "0.12rem 0.6rem", cursor: "default"
                            }}>
                                <div style={{ position: "absolute", right: 0, top: 0, bottom: 0, width: `${pct}%`, background: "rgba(244, 63, 94, 0.15)", transition: "width 0.2s" }} />
                                <span style={{ color: "var(--neg-bright)", fontWeight: 600, zIndex: 1, textShadow: "0 1px 2px rgba(0,0,0,0.8)" }}>{formatPrice(ask[0])}</span>
                                <span style={{ color: "var(--text-1)", fontWeight: 500, zIndex: 1, textShadow: "0 1px 2px rgba(0,0,0,0.8)" }}>{formatVol(ask[1])}</span>
                            </div>
                        );
                    })}
                </div>

                {/* Spread Separator */}
                <div style={{
                    padding: "0.3rem 0.6rem", display: "flex", alignItems: "center", justifyContent: "center",
                    borderTop: "1px dashed rgba(255, 255, 255, 0.1)", borderBottom: "1px dashed rgba(255, 255, 255, 0.1)",
                    color: "var(--text-main)", fontWeight: 800, fontSize: "0.6rem", background: "rgba(255, 255, 255, 0.02)",
                    margin: "0.15rem 0"
                }}>
                    SPREAD
                </div>

                {/* Bids (Buy Side) */}
                <div style={{ display: "flex", flexDirection: "column", flex: 1, justifyContent: "flex-start" }}>
                    {bids.map((bid, idx) => {
                        const pct = Math.min(100, (bid[1] / maxVol) * 100);
                        return (
                            <div key={`bid-${bid[0]}-${idx}`} style={{
                                display: "flex", justifyContent: "space-between", position: "relative",
                                padding: "0.12rem 0.6rem", cursor: "default"
                            }}>
                                <div style={{ position: "absolute", right: 0, top: 0, bottom: 0, width: `${pct}%`, background: "rgba(16, 185, 129, 0.15)", transition: "width 0.2s" }} />
                                <span style={{ color: "var(--pos)", fontWeight: 600, zIndex: 1, textShadow: "0 1px 2px rgba(0,0,0,0.8)" }}>{formatPrice(bid[0])}</span>
                                <span style={{ color: "var(--text-1)", fontWeight: 500, zIndex: 1, textShadow: "0 1px 2px rgba(0,0,0,0.8)" }}>{formatVol(bid[1])}</span>
                            </div>
                        );
                    })}
                </div>
            </div>
        </div>
    );
};
