"use client";

import React, { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
    Zap, Grid, Activity, BarChart2, Shield, Radio,
    Play, Cpu, Layers, ChevronLeft, ChevronRight, User
} from "lucide-react";
import { fetchScanStatus, ScanStatus } from "@/lib/api";
import { useSidebar } from "@/contexts/SidebarContext";

interface SidebarProps {
    onRunScan?: () => void;
    coiledCount?: number;
    surgeCount?: number;
    gammaCount?: number;
}

function relativeTime(isoString: string | undefined): string {
    if (!isoString) return "—";
    const diff = Date.now() - new Date(isoString).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return "just now";
    if (mins < 60) return `${mins}m ago`;
    return `${Math.floor(mins / 60)}h ago`;
}

export const Sidebar: React.FC<SidebarProps> = ({
    onRunScan,
    coiledCount = 0,
    surgeCount = 0,
    gammaCount = 0,
}) => {
    const pathname = usePathname();
    const { isOpen: isSidebarOpen, toggleSidebar } = useSidebar();
    const [sysClock, setSysClock] = useState<string>("");
    const [scanStatus, setScanStatus] = useState<ScanStatus | null>(null);

    useEffect(() => {
        const timer = setInterval(() => {
            const now = new Date();
            setSysClock(now.toISOString().substring(11, 23));
        }, 100);
        return () => clearInterval(timer);
    }, []);

    const loadScanStatus = useCallback(async () => {
        try {
            const s = await fetchScanStatus();
            setScanStatus(s);
        } catch (err) {
            console.error("Sidebar scan status error:", err);
        }
    }, []);

    useEffect(() => {
        loadScanStatus();
        const interval = setInterval(loadScanStatus, 30000);
        return () => clearInterval(interval);
    }, [loadScanStatus]);

    const navItems = [
        { label: "Scanner Matrix", path: "/", icon: <Grid size={16} /> },
        { label: "Altcoin RS Radar", path: "/radar", icon: <BarChart2 size={16} /> },
        { label: "Gamma Engine", path: "/gamma", icon: <Activity size={16} /> },
        { label: "Liquidity Heatmap", path: "/liquidity", icon: <Layers size={16} /> },
        { label: "Execution Blotter", path: "/edge", icon: <Shield size={16} /> },
        { label: "System Telemetry", path: "/research", icon: <Radio size={16} /> },
    ];

    const scannerIsLive = scanStatus?.status === "DONE" || scanStatus?.status === "IDLE";
    const scannerStatusLabel = scanStatus ? scanStatus.status : "LOADING";
    const symbolsScanned = scanStatus?.symbols_fetched ?? 0;
    const lastRunLabel = scanStatus?.completed_at ? relativeTime(scanStatus.completed_at) : "—";

    return (
        <aside
            style={{
                position: "fixed",
                left: 0,
                top: 0,
                bottom: 0,
                width: "var(--sidebar-width, 256px)",
                backgroundColor: "var(--surface-container-low)",
                zIndex: 50,
                display: "flex",
                flexDirection: "column",
                borderRight: "1px solid var(--outline-variant)",
                transition: "var(--sidebar-transition, all 0.3s)",
                overflow: "hidden",
            }}
        >
            <div style={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0 }}>
                {/* ── Brand Header ── */}
                <div
                    style={{
                        height: "56px",
                        padding: isSidebarOpen ? "0 0.75rem" : "0",
                        display: "flex",
                        flexDirection: "row",
                        alignItems: "center",
                        backgroundColor: "var(--surface-container-lowest)",
                        borderBottom: "1px solid var(--outline-variant)",
                        flexShrink: 0
                    }}
                >
                    <div style={{ display: "flex", alignItems: "center", gap: "0.6rem", width: "100%", justifyContent: isSidebarOpen ? "flex-start" : "center" }}>
                        <div
                            style={{
                                width: "28px", height: "28px", borderRadius: "6px",
                                backgroundColor: "rgba(0, 227, 143, 0.15)",
                                display: "flex", alignItems: "center", justifyContent: "center",
                                color: "var(--primary-fixed-dim)", flexShrink: 0
                            }}
                        >
                            <Zap size={16} fill="var(--primary-fixed-dim)" />
                        </div>
                        {isSidebarOpen && (
                            <div style={{ display: "flex", flexDirection: "column", overflow: "hidden", whiteSpace: "nowrap" }}>
                                <span className="font-label-caps" style={{ color: "var(--primary)", letterSpacing: "0.12em", fontSize: "0.82rem", lineHeight: 1.1 }}>
                                    TAPERADAR X1
                                </span>
                                <span className="font-mono-data-compact" style={{ color: "var(--on-surface-variant)", fontSize: "0.65rem", lineHeight: 1.1, marginTop: "0.1rem" }}>
                                    v4.8.2 // PRO-CORE
                                </span>
                            </div>
                        )}
                    </div>
                </div>

                {/* ── Scanner Status Box ── */}
                {isSidebarOpen && (
                    <div style={{ padding: "0.5rem 0.75rem", flexShrink: 0 }}>
                        <div
                            style={{
                                padding: "0.5rem",
                                backgroundColor: "var(--surface-container)",
                                borderRadius: "6px",
                                display: "flex",
                                flexDirection: "column",
                                gap: "0.25rem",
                            }}
                        >
                            <div className="font-label-caps" style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                                <span style={{ color: "var(--on-surface-variant)" }}>SCANNER STATUS</span>
                                <span
                                    style={{
                                        color: scannerIsLive ? "var(--primary-fixed-dim)" : "var(--warn)",
                                        display: "flex", alignItems: "center", gap: "0.25rem",
                                    }}
                                >
                                    <span
                                        style={{
                                            width: "6px", height: "6px", borderRadius: "50%",
                                            backgroundColor: scannerIsLive ? "var(--primary-fixed-dim)" : "var(--warn)",
                                            boxShadow: scannerIsLive ? "0 0 8px var(--primary-fixed-dim)" : "none",
                                        }}
                                    />
                                    {scannerStatusLabel}
                                </span>
                            </div>
                            <div
                                className="font-mono-data-compact"
                                style={{ display: "flex", alignItems: "center", justifyContent: "space-between", color: "var(--on-surface)" }}
                            >
                                <span style={{ color: "var(--on-surface-variant)" }}>SYMBOLS</span>
                                <span>{symbolsScanned > 0 ? symbolsScanned.toLocaleString() + " scanned" : "—"}</span>
                            </div>
                            <div
                                className="font-mono-data-compact"
                                style={{ display: "flex", alignItems: "center", justifyContent: "space-between", color: "var(--on-surface)" }}
                            >
                                <span style={{ color: "var(--on-surface-variant)" }}>LAST RUN</span>
                                <span>{lastRunLabel}</span>
                            </div>
                        </div>
                    </div>
                )}

                {/* ── Core Modules Label ── */}
                {isSidebarOpen && (
                    <div style={{ padding: "0.75rem 0.75rem 0.25rem", flexShrink: 0 }}>
                        <span className="font-label-caps" style={{ color: "var(--outline)", paddingLeft: "0.25rem", whiteSpace: "nowrap" }}>
                            Terminal Core Modules
                        </span>
                    </div>
                )}

                {/* ── Navigation List ── */}
                <nav style={{ display: "flex", flexDirection: "column", padding: "0 0.5rem", gap: "0.25rem", flex: 1, overflowY: "auto", overflowX: "hidden" }}>
                    {navItems.map((item) => {
                        const isActive = pathname === item.path || (item.path !== "/" && !item.path.includes("#") && pathname?.startsWith(item.path));
                        return (
                            <Link
                                key={item.label}
                                href={item.path}
                                title={isSidebarOpen ? undefined : item.label}
                                style={{
                                    display: "flex",
                                    alignItems: "center",
                                    gap: "0.75rem",
                                    textDecoration: "none",
                                    color: isActive ? "var(--primary)" : "var(--on-surface-variant)",
                                    backgroundColor: isActive ? "rgba(0, 227, 143, 0.08)" : "transparent",
                                    padding: isSidebarOpen ? "0.6rem 1rem" : "0.6rem 0",
                                    justifyContent: isSidebarOpen ? "flex-start" : "center",
                                    borderRadius: "6px",
                                    marginTop: "0.25rem",
                                    position: "relative",
                                    whiteSpace: "nowrap"
                                }}
                            >
                                {isActive && <div style={{ position: "absolute", left: 0, top: "20%", bottom: "20%", width: "3px", backgroundColor: "var(--primary-fixed-dim)", borderRadius: "0 4px 4px 0" }} />}
                                <div style={{ flexShrink: 0 }}>{item.icon}</div>
                                {isSidebarOpen && <span className="font-body-md" style={{ fontWeight: isActive ? 600 : 500 }}>{item.label}</span>}
                            </Link>
                        );
                    })}
                </nav>
            </div>

            <div style={{ padding: isSidebarOpen ? "1rem 0.75rem" : "1rem 0", display: "flex", flexDirection: "column", gap: "1rem", flexShrink: 0 }}>
                {isSidebarOpen && (
                    <div style={{ display: "flex", flexDirection: "column", gap: "0.4rem", padding: "0 0.5rem", whiteSpace: "nowrap" }}>
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                            <span className="font-label-caps" style={{ color: "var(--on-surface-variant)" }}>SYSTEM CLOCK</span>
                            <span className="font-mono-data-compact" style={{ color: "var(--primary-fixed-dim)" }}>{sysClock} UTC</span>
                        </div>
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                            <span className="font-label-caps" style={{ color: "var(--on-surface-variant)" }}>TICK BUFFER</span>
                            <span className="font-mono-data-compact" style={{ color: "var(--on-surface)" }}>{typeof symbolsScanned === 'number' ? symbolsScanned.toLocaleString() : "—"}/s</span>
                        </div>
                    </div>
                )}

                <div style={{ padding: isSidebarOpen ? "0" : "0 0.5rem" }}>
                    <button
                        onClick={onRunScan}
                        className="font-headline-sm"
                        style={{
                            width: "100%",
                            backgroundColor: scannerIsLive ? "var(--surface-container-high)" : "var(--primary-fixed-dim)",
                            color: scannerIsLive ? "var(--on-surface-variant)" : "var(--on-primary-fixed)",
                            border: scannerIsLive ? "1px solid var(--outline-variant)" : "none",
                            padding: isSidebarOpen ? "0.6rem 0" : "0.6rem 0.2rem",
                            borderRadius: "4px",
                            display: "flex",
                            justifyContent: "center",
                            alignItems: "center",
                            gap: "0.5rem",
                            cursor: scannerIsLive ? "not-allowed" : "pointer",
                            opacity: scannerIsLive ? 0.7 : 1,
                            whiteSpace: "nowrap"
                        }}
                        disabled={scannerIsLive}
                    >
                        {scannerIsLive ? <Cpu size={16} style={{ flexShrink: 0 }} /> : <Play size={16} fill="currentColor" style={{ flexShrink: 0 }} />}
                        {isSidebarOpen && (scannerIsLive ? "SCAN ACTIVE" : "RUN SCAN")}
                    </button>
                </div>

                {/* ── Sidebar Toggle Button ── */}
                <div style={{ display: "flex", justifyContent: isSidebarOpen ? "flex-end" : "center", padding: isSidebarOpen ? "0 0.5rem" : "0" }}>
                    <button
                        onClick={toggleSidebar}
                        style={{
                            width: "32px", height: "32px", borderRadius: "4px",
                            backgroundColor: "transparent", border: "1px solid var(--outline-variant)",
                            display: "flex", alignItems: "center", justifyContent: "center",
                            color: "var(--on-surface-variant)", cursor: "pointer",
                            transition: "background-color 0.2s"
                        }}
                        onMouseEnter={e => e.currentTarget.style.backgroundColor = "var(--surface-container-high)"}
                        onMouseLeave={e => e.currentTarget.style.backgroundColor = "transparent"}
                        title={isSidebarOpen ? "Collapse Sidebar" : "Expand Sidebar"}
                    >
                        {isSidebarOpen ? <ChevronLeft size={16} /> : <ChevronRight size={16} />}
                    </button>
                </div>
            </div>
        </aside>
    );
};
