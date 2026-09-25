"use client";

import React, { useState, useEffect, useCallback } from "react";
import { Send, Bell, Sliders, Webhook, Zap, RefreshCw, ChevronLeft, ChevronRight, Volume2, ShieldAlert, TrendingUp, Layers, Play } from "lucide-react";
import { apiFetch, AlertRow, fetchAlerts, fetchPendingAlerts } from "@/lib/api";
import { playAlertSound, SoundAlertType } from "@/lib/soundAlerts";

export type AlertCategory = "ALL" | "WHALES" | "OI SPIKES" | "SWEEPS";

export interface DisplayAlert {
    id: string;
    category: "WHALES" | "OI_SPIKES" | "SWEEPS" | "OTHER";
    soundType: SoundAlertType;
    badge: string;
    badgeStyle: { bg: string; color: string };
    symbol: string;
    time: string;
    price: string;
    metric: string;
    metricColor: string;
    desc: string;
    volumeUsd?: string;
}

function relativeTime(isoString: string): string {
    if (!isoString) return "just now";
    const diff = Date.now() - new Date(isoString.endsWith("Z") || isoString.includes("+") ? isoString : `${isoString}Z`).getTime();
    if (isNaN(diff)) return "just now";
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return "just now";
    if (mins < 60) return `${mins}m ago`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}h ago`;
    return `${Math.floor(hrs / 24)}d ago`;
}

// Removed MOCK_20_ALERTS completely.
function alertTypeToBadge(alertType: string): { badge: string; bg: string; color: string; category: "WHALES" | "OI_SPIKES" | "SWEEPS" | "OTHER"; soundType: SoundAlertType } {
    const t = alertType?.toUpperCase() || "";
    if (t.includes("WHALE") || t.includes("WALL") || t.includes("ENTRY")) {
        return { badge: "WHALE WALL", bg: "rgba(56, 189, 248, 0.15)", color: "var(--info)", category: "WHALES", soundType: "WALL" };
    }
    if (t.includes("SCORE") || t.includes("SURGE") || t.includes("OI")) {
        return { badge: "OI SURGE", bg: "rgba(245, 158, 11, 0.15)", color: "var(--warn)", category: "OI_SPIKES", soundType: "VOLATILITY" };
    }
    if (t.includes("SWEEP") || t.includes("BREAK") || t.includes("LIQ")) {
        return { badge: "SWEEP BLOCK", bg: "rgba(0, 227, 143, 0.15)", color: "var(--primary-fixed-dim)", category: "SWEEPS", soundType: "SWEEP" };
    }
    return { badge: alertType.replace(/_/g, " ").slice(0, 14), bg: "rgba(168, 85, 247, 0.15)", color: "var(--tertiary-fixed-dim)", category: "OTHER", soundType: "BIAS_FLIP" };
}

function mapAlert(row: AlertRow): DisplayAlert {
    const { badge, bg, color, category, soundType } = alertTypeToBadge(row.alert_type);
    const priceStr = row.price_at_alert >= 1000
        ? `$${row.price_at_alert.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
        : `$${row.price_at_alert.toFixed(4)}`;
    const metricStr = row.score_at_alert
        ? `Score ${Math.round(row.score_at_alert)}`
        : row.zone_price
            ? `Zone $${row.zone_price.toFixed(2)}`
            : row.alert_type.replace(/_/g, " ");
    const desc = row.label_at_alert
        ? `${row.label_at_alert.replace(/_/g, " ")} signal triggered. Alert type: ${row.alert_type.replace(/_/g, " ").toLowerCase()}.`
        : `${row.alert_type.replace(/_/g, " ").toLowerCase()} alert triggered for ${row.product_id}.`;
    return {
        id: row.id,
        category,
        soundType,
        badge,
        badgeStyle: { bg, color },
        symbol: row.product_id,
        time: relativeTime(row.created_at),
        price: priceStr,
        metric: metricStr,
        metricColor: color,
        desc,
    };
}

interface AlphaStreamDockProps {
    isCollapsed: boolean;
    onToggle: () => void;
}

export const AlphaStreamDock: React.FC<AlphaStreamDockProps> = ({ isCollapsed, onToggle }) => {
    const [activeFilter, setActiveFilter] = useState<AlertCategory>("ALL");
    const [alerts, setAlerts] = useState<DisplayAlert[]>([]);
    const [pendingCount, setPendingCount] = useState<number>(0);
    const [loading, setLoading] = useState<boolean>(false);
    const [error, setError] = useState<string | null>(null);
    const [telegramStatus, setTelegramStatus] = useState<"CONNECTED" | "OFFLINE" | "CHECKING">("CONNECTED");

    const loadAlerts = useCallback(async () => {
        try {
            const [rows, pending] = await Promise.all([
                fetchAlerts(1, 40),
                fetchPendingAlerts(),
            ]);
            if (rows && rows.length > 0) {
                const mapped = rows.map(mapAlert);
                setAlerts(mapped);
            } else {
                setAlerts([]);
            }
            setPendingCount(pending?.length || 0);
            setError(null);
            setTelegramStatus("CONNECTED");
        } catch (err: any) {
            setAlerts([]);
            setTelegramStatus("OFFLINE");
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        loadAlerts();
        const interval = setInterval(loadAlerts, 12000);
        return () => clearInterval(interval);
    }, [loadAlerts]);

    // Active Category Filter Logic
    const filteredAlerts = alerts.filter((item) => {
        if (activeFilter === "ALL") return true;
        if (activeFilter === "WHALES") return item.category === "WHALES";
        if (activeFilter === "OI SPIKES") return item.category === "OI_SPIKES";
        if (activeFilter === "SWEEPS") return item.category === "SWEEPS";
        return true;
    });

    if (isCollapsed) {
        return (
            <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem", height: "100%" }}>
                <div
                    style={{
                        backgroundColor: "var(--surface-container-low)",
                        borderRadius: "6px",
                        padding: "0.5rem",
                        boxShadow: "0 2px 6px rgba(0,0,0,0.3)",
                        display: "flex",
                        flexDirection: "column",
                        alignItems: "center",
                        gap: "1rem",
                        border: "1px solid var(--outline-variant)",
                        height: "100%",
                        minHeight: "200px"
                    }}
                >
                    <button
                        onClick={onToggle}
                        style={{ background: "none", border: "none", color: "var(--outline)", cursor: "pointer", display: "flex", padding: 0 }}
                        title="Expand Alerts"
                    >
                        <ChevronLeft size={16} />
                    </button>
                    <div style={{ writingMode: "vertical-rl", transform: "rotate(180deg)", color: "var(--on-surface-variant)", letterSpacing: "2px", fontSize: "10px", fontWeight: 600, display: "flex", alignItems: "center", gap: "10px" }}>
                        <Bell size={12} color="var(--primary-fixed-dim)" />
                        ALERTS ({alerts.length})
                    </div>
                </div>
            </div>
        );
    }

    return (
        <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
            {/* ── Live Alert Feed Card ── */}
            <div
                style={{
                    backgroundColor: "var(--surface-container-low)",
                    borderRadius: "6px",
                    padding: "0.5rem",
                    boxShadow: "0 2px 6px rgba(0,0,0,0.3)",
                    display: "flex",
                    flexDirection: "column",
                    gap: "0.5rem",
                    border: "1px solid var(--outline-variant)",
                }}
            >
                {/* Header row */}
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: "0.35rem" }}>
                        <Bell size={13} color="var(--primary-fixed-dim)" />
                        <span className="font-label-caps" style={{ color: "var(--on-surface)", fontWeight: 700 }}>
                            ALPHA ALERT STREAM
                        </span>
                    </div>
                    <div style={{ display: "flex", alignItems: "center", gap: "0.35rem" }}>
                        {loading && <RefreshCw size={11} style={{ animation: "spin 1s linear infinite", color: "var(--outline)" }} />}
                        <span
                            className="font-mono-data-compact"
                            style={{
                                padding: "0.1rem 0.35rem",
                                backgroundColor: "rgba(0, 245, 155, 0.15)",
                                color: "var(--primary-fixed-dim)",
                                borderRadius: "3px",
                                fontWeight: 700,
                                fontSize: "9px",
                            }}
                        >
                            20 ALERTS
                        </span>
                        {pendingCount > 0 && (
                            <span
                                className="font-mono-data-compact"
                                style={{
                                    padding: "0.1rem 0.35rem",
                                    backgroundColor: "rgba(245, 158, 11, 0.15)",
                                    color: "var(--warn)",
                                    borderRadius: "3px",
                                    fontWeight: 700,
                                    fontSize: "9px",
                                }}
                            >
                                {pendingCount} PENDING
                            </span>
                        )}
                        <button
                            onClick={onToggle}
                            style={{ background: "none", border: "none", color: "var(--outline)", cursor: "pointer", display: "flex", padding: 0 }}
                            title="Collapse Alerts"
                        >
                            <ChevronRight size={13} />
                        </button>
                    </div>
                </div>

                {/* Alpha Filter Sub-Tabs */}
                <div
                    style={{
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "space-between",
                        backgroundColor: "var(--surface-container-lowest)",
                        padding: "0.2rem",
                        borderRadius: "4px",
                        gap: "2px"
                    }}
                >
                    {(["ALL", "WHALES", "OI SPIKES", "SWEEPS"] as const).map((tab) => {
                        const isTabActive = activeFilter === tab;
                        let count = alerts.length;
                        if (tab === "WHALES") count = alerts.filter(a => a.category === "WHALES").length;
                        if (tab === "OI SPIKES") count = alerts.filter(a => a.category === "OI_SPIKES").length;
                        if (tab === "SWEEPS") count = alerts.filter(a => a.category === "SWEEPS").length;

                        return (
                            <button
                                key={tab}
                                onClick={() => setActiveFilter(tab)}
                                className="font-label-caps"
                                style={{
                                    flex: 1,
                                    padding: "0.25rem 0",
                                    textAlign: "center",
                                    fontSize: "9px",
                                    borderRadius: "3px",
                                    border: "none",
                                    cursor: "pointer",
                                    backgroundColor: isTabActive ? "var(--surface-container-high)" : "transparent",
                                    color: isTabActive ? "var(--primary-fixed-dim)" : "var(--on-surface-variant)",
                                    fontWeight: isTabActive ? 700 : 500,
                                    transition: "all var(--dur-fast) var(--ease-out)",
                                }}
                            >
                                {tab === "ALL" ? `ALL (20)` : `${tab} (${count})`}
                            </button>
                        );
                    })}
                </div>

                {/* Alert Cards Stream */}
                <div
                    style={{
                        display: "flex",
                        flexDirection: "column",
                        gap: "0.35rem",
                        maxHeight: "520px",
                        overflowY: "auto",
                        paddingRight: "0.2rem",
                    }}
                >
                    {filteredAlerts.map((item) => (
                        <div
                            key={item.id}
                            style={{
                                padding: "0.5rem",
                                backgroundColor: "var(--surface-container)",
                                borderRadius: "5px",
                                display: "flex",
                                flexDirection: "column",
                                gap: "0.25rem",
                                cursor: "pointer",
                                border: "1px solid transparent",
                                transition: "all var(--dur-fast) var(--ease-out)",
                            }}
                            onMouseEnter={(e) => {
                                e.currentTarget.style.backgroundColor = "var(--surface-container-high)";
                                e.currentTarget.style.borderColor = "var(--outline-variant)";
                            }}
                            onMouseLeave={(e) => {
                                e.currentTarget.style.backgroundColor = "var(--surface-container)";
                                e.currentTarget.style.borderColor = "transparent";
                            }}
                        >
                            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                                <div style={{ display: "flex", alignItems: "center", gap: "0.35rem" }}>
                                    <span
                                        className="font-label-caps"
                                        style={{
                                            padding: "0.1rem 0.35rem",
                                            borderRadius: "3px",
                                            fontSize: "9px",
                                            fontWeight: 700,
                                            backgroundColor: item.badgeStyle.bg,
                                            color: item.badgeStyle.color,
                                        }}
                                    >
                                        {item.badge}
                                    </span>
                                    <span
                                        className="font-mono-data-primary"
                                        style={{ fontWeight: 700, color: "var(--on-surface)" }}
                                    >
                                        {item.symbol}
                                    </span>
                                </div>

                                <div style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                                    {/* Play Sound Button */}
                                    <button
                                        onClick={(e) => {
                                            e.stopPropagation();
                                            playAlertSound(item.soundType);
                                        }}
                                        style={{
                                            background: "none",
                                            border: "none",
                                            color: item.badgeStyle.color,
                                            cursor: "pointer",
                                            padding: "2px",
                                            display: "flex",
                                            alignItems: "center"
                                        }}
                                        title={`Play ${item.soundType} Sound Alert`}
                                    >
                                        <Volume2 size={12} />
                                    </button>

                                    <span className="font-mono-data-compact" style={{ color: "var(--outline)" }}>
                                        {item.time}
                                    </span>
                                </div>
                            </div>

                            <div
                                className="font-mono-data-compact"
                                style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between" }}
                            >
                                <span style={{ color: "var(--on-surface-variant)" }}>
                                    Price: <strong style={{ color: "var(--on-surface)" }}>{item.price}</strong>
                                </span>
                                <span style={{ color: item.metricColor, fontWeight: 700 }}>
                                    {item.metric}
                                </span>
                            </div>

                            <p
                                className="font-body-sm"
                                style={{
                                    margin: 0,
                                    fontSize: "11px",
                                    color: "var(--on-surface-variant)",
                                    lineHeight: "1.3",
                                }}
                            >
                                {item.desc}
                            </p>
                        </div>
                    ))}
                </div>
            </div>

            {/* ── Push Dispatch & Telegram Webhook Panel ── */}
            <div
                style={{
                    backgroundColor: "var(--surface-container-low)",
                    borderRadius: "6px",
                    padding: "0.5rem",
                    boxShadow: "0 2px 6px rgba(0,0,0,0.3)",
                    display: "flex",
                    flexDirection: "column",
                    gap: "0.4rem",
                    border: "1px solid var(--outline-variant)",
                }}
            >
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: "0.35rem" }}>
                        <Zap size={14} color="var(--primary-fixed-dim)" />
                        <span
                            className="font-label-caps"
                            style={{ color: "var(--on-surface)", fontWeight: 700 }}
                        >
                            AUTOMATED DISPATCH
                        </span>
                    </div>
                    <span
                        className="font-mono-data-compact"
                        style={{
                            padding: "0.1rem 0.35rem",
                            backgroundColor: "rgba(0, 245, 155, 0.15)",
                            color: "var(--primary-fixed-dim)",
                            borderRadius: "3px",
                            fontWeight: 700,
                            fontSize: "9px",
                        }}
                    >
                        CONNECTED
                    </span>
                </div>

                <p
                    className="font-body-sm"
                    style={{ margin: 0, color: "var(--on-surface-variant)", fontSize: "11px", lineHeight: "1.35" }}
                >
                    Forward Tier-1 quantified triggers (&gt;92 score) directly to connected low-latency endpoints.
                </p>

                <div style={{ display: "flex", flexDirection: "column", gap: "0.25rem" }}>
                    <div
                        className="font-mono-data-compact"
                        style={{
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "space-between",
                            padding: "0.25rem 0.4rem",
                            backgroundColor: "var(--surface-container)",
                            borderRadius: "4px",
                        }}
                    >
                        <div style={{ display: "flex", alignItems: "center", gap: "0.35rem" }}>
                            <Send size={12} color="var(--primary-fixed-dim)" />
                            <span>TG BOT @TapeRadarAlerts</span>
                        </div>
                        <span style={{ color: "var(--primary-fixed-dim)", fontWeight: 700 }}>
                            CONNECTED
                        </span>
                    </div>
                </div>
            </div>
        </div>
    );
};
