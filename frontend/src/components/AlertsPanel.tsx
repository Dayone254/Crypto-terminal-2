"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Bell, BellRing, Check, Moon } from "lucide-react";
import { AlertRow, dismissAlert, fetchAlerts, fetchPendingAlerts } from "@/lib/api";

/** Presentation per alert type. */
const ALERT_STYLES: Record<string, { label: string; color: string; bg: string }> = {
    ZONE_A_ENTRY: { label: "ZONE A", color: "#10B981", bg: "rgba(16,185,129,0.14)" },
    ZONE_B_ENTRY: { label: "ZONE B", color: "#34D399", bg: "rgba(52,211,153,0.14)" },
    ZONE_A_APPROACH: { label: "APPROACH", color: "#06B6D4", bg: "rgba(6,182,212,0.14)" },
    BREAKOUT_WATCH: { label: "BREAKOUT", color: "#3B82F6", bg: "rgba(59,130,246,0.14)" },
    INVALIDATION: { label: "INVALIDATED", color: "#F43F5E", bg: "rgba(244,63,94,0.14)" },
    DIGEST: { label: "DIGEST", color: "#A855F7", bg: "rgba(168,85,247,0.14)" },
};

function styleFor(alertType: string) {
    return (
        ALERT_STYLES[alertType] ?? {
            label: alertType.replace(/_/g, " "),
            color: "#94A3B8",
            bg: "rgba(148,163,184,0.12)",
        }
    );
}

function timeAgo(iso?: string | null): string {
    if (!iso) return "";
    const then = new Date(iso.endsWith("Z") || iso.includes("+") ? iso : `${iso}Z`).getTime();
    if (Number.isNaN(then)) return "";
    const secs = Math.max(0, Math.floor((Date.now() - then) / 1000));
    if (secs < 60) return `${secs}s ago`;
    if (secs < 3600) return `${Math.floor(secs / 60)}m ago`;
    if (secs < 86400) return `${Math.floor(secs / 3600)}h ago`;
    return `${Math.floor(secs / 86400)}d ago`;
}

function priceLabel(value: number | null | undefined): string {
    if (value === null || value === undefined) return "─";
    const n = Number(value);
    if (!Number.isFinite(n)) return "─";
    if (n < 0.0001) return `$${n.toFixed(6)}`;
    if (n < 1) return `$${n.toFixed(5)}`;
    if (n < 10) return `$${n.toFixed(3)}`;
    return `$${n.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
}

export const AlertsPanel: React.FC = () => {
    const [pending, setPending] = useState<AlertRow[]>([]);
    const [recent, setRecent] = useState<AlertRow[]>([]);
    const [busyId, setBusyId] = useState<string | null>(null);

    const load = useCallback(async () => {
        try {
            const [pendingData, recentData] = await Promise.all([
                fetchPendingAlerts(),
                fetchAlerts(1, 8),
            ]);
            setPending(pendingData);
            setRecent(recentData.filter((a) => !a.dismissed_by_user).slice(0, 8));
        } catch {
            /* keep the last good render */
        }
    }, []);

    useEffect(() => {
        load();
        const interval = setInterval(load, 30000);
        return () => clearInterval(interval);
    }, [load]);

    const handleDismiss = async (id: string) => {
        setBusyId(id);
        try {
            await dismissAlert(id);
            await load();
        } catch {
            /* ignore — the next poll re-syncs */
        } finally {
            setBusyId(null);
        }
    };

    // Pending first, de-duplicated, capped for the sidebar.
    const seen = new Set<string>();
    const visible = [...pending, ...recent]
        .filter((a) => {
            if (seen.has(a.id)) return false;
            seen.add(a.id);
            return true;
        })
        .slice(0, 10);

    return (
        <div style={{ background: "#080A0F", borderRadius: 0, overflow: "hidden" }}>
            {/* Header */}
            <div
                style={{
                    background: "#0B0F19",
                    padding: "1rem 1.25rem",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                }}
            >
                <div style={{ display: "flex", alignItems: "center", gap: "0.6rem" }}>
                    {pending.length > 0 ? (
                        <BellRing size={15} color="var(--accent-amber)" />
                    ) : (
                        <Bell size={15} color="var(--accent-cyan)" />
                    )}
                    <span
                        style={{
                            fontSize: "0.72rem",
                            fontWeight: 800,
                            letterSpacing: "0.06em",
                            color: "var(--text-main)",
                        }}
                    >
                        ALERTS
                    </span>
                </div>
                <span
                    className="mono"
                    style={{
                        fontSize: "0.62rem",
                        fontWeight: 800,
                        padding: "0.15rem 0.5rem",
                        borderRadius: "5px",
                        color: pending.length > 0 ? "var(--accent-amber)" : "var(--text-dim)",
                        background:
                            pending.length > 0 ? "rgba(245,158,11,0.15)" : "rgba(148,163,184,0.1)",
                    }}
                >
                    {pending.length} PENDING
                </span>
            </div>

            <div style={{ padding: "0.75rem 1.25rem 1rem" }}>
                {/* Quiet-hours notice */}
                {pending.length > 0 && (
                    <div
                        style={{
                            display: "flex",
                            alignItems: "flex-start",
                            gap: "0.5rem",
                            padding: "0.6rem 0.7rem",
                            marginBottom: "0.75rem",
                            background: "rgba(245,158,11,0.08)",
                            borderRadius: 0,
                        }}
                    >
                        <Moon size={13} color="var(--accent-amber)" style={{ marginTop: 2, flexShrink: 0 }} />
                        <span style={{ fontSize: "0.66rem", color: "var(--accent-amber)", lineHeight: 1.45 }}>
                            Held during quiet hours — delivered as a morning digest.
                        </span>
                    </div>
                )}

                {/* List */}
                {recent.length === 0 && pending.length === 0 ? (
                    <div
                        style={{
                            padding: "1.5rem 0",
                            textAlign: "center",
                            fontSize: "0.7rem",
                            color: "var(--text-dim)",
                        }}
                    >
                        No alerts yet.
                        <div style={{ marginTop: "0.35rem", fontSize: "0.62rem" }}>
                            Fires when price enters a ladder zone.
                        </div>
                    </div>
                ) : (
                    <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                        {visible.map((alert) => {
                                const s = styleFor(alert.alert_type);
                                const isPending = alert.delivered_at === null || alert.delivered_at === undefined;
                                return (
                                    <div
                                        key={alert.id}
                                        style={{
                                            display: "flex",
                                            alignItems: "center",
                                            gap: "0.6rem",
                                            padding: "0.55rem 0.65rem",
                                            background: "#0B0F19",
                                        }}
                                    >
                                        <div style={{ flex: 1, minWidth: 0 }}>
                                            <div
                                                style={{
                                                    display: "flex",
                                                    alignItems: "center",
                                                    gap: "0.45rem",
                                                    marginBottom: "0.25rem",
                                                }}
                                            >
                                                <span
                                                    style={{
                                                        fontSize: "0.58rem",
                                                        fontWeight: 900,
                                                        letterSpacing: "0.04em",
                                                        color: s.color,
                                                        background: s.bg,
                                                        padding: "0.1rem 0.35rem",
                                                        borderRadius: "4px",
                                                        whiteSpace: "nowrap",
                                                    }}
                                                >
                                                    {s.label}
                                                </span>
                                                <Link
                                                    href={`/market/${encodeURIComponent(alert.product_id)}`}
                                                    style={{
                                                        fontSize: "0.72rem",
                                                        fontWeight: 800,
                                                        color: "var(--text-main)",
                                                        textDecoration: "none",
                                                        overflow: "hidden",
                                                        textOverflow: "ellipsis",
                                                        whiteSpace: "nowrap",
                                                    }}
                                                >
                                                    {alert.product_id}
                                                </Link>
                                            </div>
                                            <div
                                                className="mono"
                                                style={{
                                                    fontSize: "0.62rem",
                                                    color: "var(--text-dim)",
                                                    display: "flex",
                                                    gap: "0.6rem",
                                                    flexWrap: "wrap",
                                                }}
                                            >
                                                <span>@ {priceLabel(alert.price_at_alert)}</span>
                                                {alert.zone_price !== null && (
                                                    <span>zone {priceLabel(alert.zone_price)}</span>
                                                )}
                                                {alert.score_at_alert !== null && (
                                                    <span>score {Math.round(alert.score_at_alert)}</span>
                                                )}
                                                <span>{timeAgo(alert.created_at)}</span>
                                            </div>
                                        </div>

                                        {isPending && (
                                            <button
                                                type="button"
                                                title="Dismiss"
                                                disabled={busyId === alert.id}
                                                onClick={() => handleDismiss(alert.id)}
                                                style={{
                                                    flexShrink: 0,
                                                    display: "flex",
                                                    alignItems: "center",
                                                    justifyContent: "center",
                                                    width: 24,
                                                    height: 24,
                                                    border: "none",
                                                    borderRadius: "5px",
                                                    cursor: busyId === alert.id ? "wait" : "pointer",
                                                    background: "rgba(6,182,212,0.12)",
                                                    color: "var(--accent-cyan)",
                                                    opacity: busyId === alert.id ? 0.5 : 1,
                                                }}
                                            >
                                                <Check size={12} />
                                            </button>
                                        )}
                                    </div>
                                );
                            })}
                    </div>
                )}
            </div>
        </div>
    );
};

export default AlertsPanel;
