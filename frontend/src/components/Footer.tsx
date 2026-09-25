"use client";

import React, { useEffect, useState, useCallback } from "react";
import { apiFetch, fetchScanStatus, ScanStatus } from "@/lib/api";

function currentSession(): string {
    const hour = new Date().getUTCHours();
    if (hour >= 22 || hour < 0) return "OFF HOURS";
    if (hour < 7) return "ASIA";
    if (hour < 12) return "LDN";
    if (hour < 17) return "LDN/NY OVERLAP";
    if (hour < 22) return "NY";
    return "OFF HOURS";
}

function relativeTime(isoString: string | undefined): string {
    if (!isoString) return "—";
    const diff = Date.now() - new Date(isoString).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return "just now";
    if (mins < 60) return `${mins}m ago`;
    return `${Math.floor(mins / 60)}h ago`;
}

export const Footer: React.FC = () => {
    const [session, setSession] = useState<string>(currentSession());
    const [apiStatus, setApiStatus] = useState<"OK" | "ERROR" | "CHECKING">("CHECKING");
    const [scanStatus, setScanStatus] = useState<ScanStatus | null>(null);

    const loadStatus = useCallback(async () => {
        setSession(currentSession());

        const [healthRes, scanRes] = await Promise.allSettled([
            apiFetch("/api/v1/health"),
            fetchScanStatus(),
        ]);

        if (healthRes.status === "fulfilled" && healthRes.value.ok) {
            setApiStatus("OK");
        } else {
            setApiStatus("ERROR");
        }

        if (scanRes.status === "fulfilled") {
            setScanStatus(scanRes.value);
        }
    }, []);

    useEffect(() => {
        loadStatus();
        const interval = setInterval(loadStatus, 15000);
        return () => clearInterval(interval);
    }, [loadStatus]);

    const engineLabel = () => {
        if (!scanStatus) return "—";
        if (scanStatus.duration_seconds !== undefined && scanStatus.duration_seconds !== null) {
            return `TAPE-X ${scanStatus.duration_seconds.toFixed(1)}s LAST RUN`;
        }
        return `TAPE-X ${scanStatus.status}`;
    };

    const symbolsLabel = () => {
        if (!scanStatus || !scanStatus.symbols_fetched) return "0 PENDING";
        return `${scanStatus.symbols_fetched} SCANNED`;
    };

    return (
        <footer
            style={{
                position: "fixed",
                bottom: 0,
                left: "var(--sidebar-width, 256px)",
                right: 0,
                height: "32px",
                backgroundColor: "var(--surface-container-lowest)",
                borderTop: "1px solid var(--outline-variant)",
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                padding: "0 1.25rem",
                zIndex: 40,
                transition: "var(--sidebar-transition, all 0.3s)",
                boxShadow: "0 -1px 8px rgba(0,0,0,0.3)",
            }}
        >
            <div
                className="font-mono-data-compact"
                style={{ display: "flex", alignItems: "center", gap: "1.25rem", color: "var(--on-surface-variant)" }}
            >
                <span>SESSION: <strong style={{ color: "var(--on-surface)" }}>{session}</strong></span>
                <span>
                    ORD ROUTER:{" "}
                    <strong style={{ color: apiStatus === "OK" ? "var(--primary-fixed-dim)" : apiStatus === "ERROR" ? "var(--secondary)" : "var(--outline)" }}>
                        {apiStatus === "OK" ? "ONLINE" : apiStatus === "ERROR" ? "ERROR" : "..."}
                    </strong>
                </span>
                <span>ENGINE: <strong style={{ color: "var(--primary-fixed-dim)" }}>{engineLabel()}</strong></span>
                <span>
                    REST FEED:{" "}
                    <strong style={{ color: apiStatus === "OK" ? "var(--primary-fixed-dim)" : "var(--secondary)" }}>
                        {apiStatus === "OK" ? "OK (200)" : apiStatus === "ERROR" ? "ERROR" : "CHECKING"}
                    </strong>
                </span>
            </div>

            <div
                className="font-mono-data-compact"
                style={{ display: "flex", alignItems: "center", gap: "1rem", color: "var(--on-surface-variant)" }}
            >
                <span>SCAN QUEUE: <strong style={{ color: "var(--on-surface)" }}>{symbolsLabel()}</strong></span>
                {scanStatus?.completed_at && (
                    <span>LAST SCAN: <strong style={{ color: "var(--on-surface)" }}>{relativeTime(scanStatus.completed_at)}</strong></span>
                )}
                <span
                    style={{
                        color: apiStatus === "OK" ? "var(--primary-fixed-dim)" : "var(--outline)",
                        display: "flex",
                        alignItems: "center",
                        gap: "0.25rem",
                    }}
                >
                    <span
                        style={{
                            width: "6px",
                            height: "6px",
                            borderRadius: "50%",
                            backgroundColor: apiStatus === "OK" ? "var(--primary-fixed-dim)" : "var(--outline)",
                        }}
                    />
                    {apiStatus === "OK" ? "ALL CLUSTERS OPERATIONAL" : "BACKEND UNREACHABLE"}
                </span>
            </div>
        </footer>
    );
};
