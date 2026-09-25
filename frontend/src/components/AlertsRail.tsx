"use client";

import React, { useState } from "react";
import { Bell, ArrowRight } from "lucide-react";

export interface AlertItem {
    id: string;
    symbol: string;
    title: string;
    subtitle: string;
    timeAgo: string;
    category: "GAMMA" | "FLOW" | "VOL";
    dotColor: string;
}

const MOCK_ALERTS: AlertItem[] = [
    { id: "1", symbol: "BTC-USD", title: "Gamma zone entered", subtitle: "$88,412 → $88,390", timeAgo: "12m ago", category: "GAMMA", dotColor: "#10b981" },
    { id: "2", symbol: "BTC-USD", title: "Put wall increased", subtitle: "$85K +18.2M GEX", timeAgo: "19m ago", category: "GAMMA", dotColor: "#f43f5e" },
    { id: "3", symbol: "XRP-USD", title: "Dealer skew changed", subtitle: "Score 74", timeAgo: "31m ago", category: "FLOW", dotColor: "#38bdf8" },
    { id: "4", symbol: "BTC-USD", title: "Call wall added", subtitle: "$90K +12.6M GEX", timeAgo: "47m ago", category: "GAMMA", dotColor: "#10b981" },
    { id: "5", symbol: "ETH-USD", title: "Volatility spike", subtitle: "IV +8.4%", timeAgo: "1h ago", category: "VOL", dotColor: "#f59e0b" },
    { id: "6", symbol: "BTC-USD", title: "Gamma flip approaching", subtitle: "$79.9K", timeAgo: "2h ago", category: "GAMMA", dotColor: "#f43f5e" },
    { id: "7", symbol: "SOL-USD", title: "Flow imbalance", subtitle: "Net -$32.4M", timeAgo: "2h ago", category: "FLOW", dotColor: "#38bdf8" },
    { id: "8", symbol: "BTC-USD", title: "Dealer inventory shift", subtitle: "Long gamma → neutral", timeAgo: "3h ago", category: "GAMMA", dotColor: "#a855f7" },
];

export const AlertsRail: React.FC = () => {
    const [activeTab, setActiveTab] = useState<"ALL" | "GAMMA" | "FLOW" | "VOL">("ALL");

    const filteredAlerts = MOCK_ALERTS.filter(
        (item) => activeTab === "ALL" || item.category === activeTab
    );

    return (
        <aside style={{
            width: "280px",
            background: "#070A10",
            borderLeft: "1px solid rgba(255, 255, 255, 0.07)",
            display: "flex",
            flexDirection: "column",
            justifyContent: "space-between",
            padding: "1.25rem 1rem",
            userSelect: "none"
        }}>
            {/* Top Header & Filter Tabs */}
            <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                        <Bell size={16} color="#38bdf8" />
                        <span style={{ fontSize: "0.85rem", fontWeight: 900, color: "#f8fafc", letterSpacing: "0.04em" }}>
                            ALERTS
                        </span>
                    </div>
                    <span style={{
                        background: "rgba(56, 189, 248, 0.15)",
                        color: "#38bdf8",
                        border: "1px solid rgba(56, 189, 248, 0.3)",
                        fontSize: "0.65rem",
                        fontWeight: 800,
                        padding: "0.15rem 0.45rem",
                        borderRadius: "10px"
                    }}>
                        8
                    </span>
                </div>

                {/* Filter Pills */}
                <div style={{ display: "flex", gap: "0.35rem" }}>
                    {(["ALL", "GAMMA", "FLOW", "VOL"] as const).map((tab) => {
                        const isActive = activeTab === tab;
                        return (
                            <button
                                key={tab}
                                onClick={() => setActiveTab(tab)}
                                style={{
                                    flex: 1,
                                    padding: "0.35rem 0",
                                    fontSize: "0.62rem",
                                    fontWeight: 800,
                                    borderRadius: "16px",
                                    border: isActive ? "1px solid #38bdf8" : "1px solid rgba(255, 255, 255, 0.08)",
                                    background: isActive ? "rgba(56, 189, 248, 0.15)" : "rgba(255, 255, 255, 0.02)",
                                    color: isActive ? "#38bdf8" : "#64748b",
                                    cursor: "pointer",
                                    transition: "all 0.15s ease"
                                }}
                            >
                                {tab}
                            </button>
                        );
                    })}
                </div>

                {/* Alert Feed Items */}
                <div style={{ display: "flex", flexDirection: "column", gap: "0.85rem", marginTop: "0.5rem" }}>
                    {filteredAlerts.map((alert) => (
                        <div key={alert.id} style={{ display: "flex", flexDirection: "column", gap: "0.2rem" }}>
                            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                                <div style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                                    <span style={{
                                        width: "6px",
                                        height: "6px",
                                        borderRadius: "50%",
                                        background: alert.dotColor,
                                        boxShadow: `0 0 6px ${alert.dotColor}`
                                    }} />
                                    <span style={{ fontSize: "0.72rem", fontWeight: 800, color: "#f8fafc" }}>
                                        {alert.symbol}
                                    </span>
                                </div>
                                <span style={{ fontSize: "0.62rem", color: "#475569" }}>
                                    {alert.timeAgo}
                                </span>
                            </div>
                            <div style={{ fontSize: "0.7rem", color: "#cbd5e1", paddingLeft: "0.9rem" }}>
                                {alert.title}
                            </div>
                            <div style={{ fontSize: "0.65rem", color: "#64748b", paddingLeft: "0.9rem" }}>
                                {alert.subtitle}
                            </div>
                        </div>
                    ))}
                </div>
            </div>

            {/* Bottom Action Button */}
            <button style={{
                width: "100%",
                padding: "0.65rem",
                borderRadius: "8px",
                background: "rgba(255, 255, 255, 0.03)",
                border: "1px solid rgba(255, 255, 255, 0.08)",
                color: "#94a3b8",
                fontSize: "0.72rem",
                fontWeight: 700,
                cursor: "pointer",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                gap: "0.4rem",
                transition: "all 0.15s ease"
            }}>
                <span>View all alerts</span>
                <ArrowRight size={13} color="#94a3b8" />
            </button>
        </aside>
    );
};
