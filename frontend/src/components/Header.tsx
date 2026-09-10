"use client";

import React, { useEffect, useState } from "react";
import { Activity, Clock, LayoutGrid, Play, RefreshCw, Server, Zap, Settings } from "lucide-react";
import { ScanStatus, triggerScan } from "@/lib/api";
import Link from "next/link";
import ScoringEditor from "./ScoringEditor";

interface HeaderProps {
    status: ScanStatus | null;
    candidateCount: number;
    pinnedCount: number;
    onScanTriggered: () => void;
}

export const Header: React.FC<HeaderProps> = ({
    status,
    candidateCount,
    pinnedCount,
    onScanTriggered,
}) => {
    const [nairobiTime, setNairobiTime] = useState<string>("");
    const [isTriggering, setIsTriggering] = useState(false);
    const [editorOpen, setEditorOpen] = useState(false);

    useEffect(() => {
        const updateClock = () => {
            const now = new Date();
            const timeStr = now.toLocaleTimeString("en-GB", {
                timeZone: "Africa/Nairobi",
                hour: "2-digit",
                minute: "2-digit",
                second: "2-digit",
            });
            setNairobiTime(timeStr);
        };
        updateClock();
        const interval = setInterval(updateClock, 1000);
        return () => clearInterval(interval);
    }, []);

    const handleRunScan = async () => {
        try {
            setIsTriggering(true);
            await triggerScan();
            onScanTriggered();
        } catch (err) {
            console.error("Scan trigger error:", err);
        } finally {
            setIsTriggering(false);
        }
    };

    const isScanning = status?.status === "RUNNING" || isTriggering;

    return (
        <header className="app-header">
            <div className="brand-title" style={{ whiteSpace: "nowrap" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "0.6rem" }}>
                    <div style={{ background: "rgba(6,182,212,0.15)", border: "none", width: "32px", height: "32px", display: "flex", alignItems: "center", justifyContent: "center" }}>
                        <Zap size={18} color="#06B6D4" fill="#06B6D4" />
                    </div>
                    <span style={{ letterSpacing: "-0.03em", fontWeight: 800 }}>TAPERADAR X1</span>
                </div>
                <span className="brand-badge" style={{ whiteSpace: "nowrap", height: "32px", display: "flex", alignItems: "center", padding: "0 0.45rem" }}>SPOT</span>
            </div>

            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                {/* Stats summary ribbon */}
                <div className="mono" style={{ display: "flex", alignItems: "center", gap: "0.6rem", fontSize: "0.72rem", color: "var(--text-muted)", height: "32px", whiteSpace: "nowrap", borderRight: "1px solid rgba(255,255,255,0.08)", paddingRight: "0.6rem" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: "0.35rem" }}>
                        <Server size={12} color="var(--text-dim)" />
                        <span style={{ color: "var(--text-dim)" }}>UNIVERSE:</span>{" "}
                        <span style={{ color: "#FFF", fontWeight: 700 }}>402</span>
                    </div>
                    <div style={{ display: "flex", alignItems: "center", gap: "0.35rem" }}>
                        <span style={{ color: "var(--text-dim)" }}>SETUPS:</span>{" "}
                        <span style={{ color: "var(--accent-emerald)", fontWeight: 800 }}>
                            {candidateCount}
                        </span>
                    </div>
                    <div style={{ display: "flex", alignItems: "center", gap: "0.35rem" }}>
                        <span style={{ color: "var(--text-dim)" }}>PINNED:</span>{" "}
                        <span style={{ color: "var(--accent-amber)", fontWeight: 800 }}>
                            {pinnedCount}
                        </span>
                    </div>
                    <div style={{ display: "flex", alignItems: "center", gap: "0.3rem", color: "var(--accent-emerald)" }}>
                        <Activity size={12} />
                        <span>11ms</span>
                    </div>
                </div>

                {/* Nairobi Clock */}
                <div
                    className="mono"
                    style={{
                        display: "flex",
                        alignItems: "center",
                        gap: "0.4rem",
                        fontSize: "0.72rem",
                        color: "var(--text-muted)",
                        background: "rgba(14, 20, 36, 0.8)",
                        padding: "0 0.75rem",
                        height: "32px",
                        whiteSpace: "nowrap"
                    }}
                >
                    <Clock size={13} color="#06B6D4" />
                    <span style={{ color: "var(--text-dim)" }}>NBO</span>
                    <span style={{ color: "#FFF", fontWeight: 700 }}>
                        {nairobiTime || "00:00:00"}
                    </span>
                </div>

                {/* Status Indicator */}
                <div style={{ height: "32px", display: "flex", alignItems: "center", padding: "0 0.75rem", whiteSpace: "nowrap" }} className={`status-pill ${isScanning ? "running" : "done"}`}>
                    <span className="status-pulse" />
                    <span>{isScanning ? "SCANNING..." : "READY"}</span>
                </div>

                {/* Links Container */}
                <div style={{ display: "flex", gap: "0.35rem" }}>
                    <Link
                        href="/edge"
                        style={{
                            display: "flex",
                            alignItems: "center",
                            gap: "0.4rem",
                            background: "rgba(16,185,129,0.07)",
                            color: "#10B981",
                            padding: "0 0.75rem",
                            height: "32px",
                            fontSize: "0.72rem",
                            fontWeight: 800,
                            textDecoration: "none",
                            letterSpacing: "0.04em",
                            whiteSpace: "nowrap"
                        }}
                    >
                        <Activity size={13} />
                        EDGE
                    </Link>

                    <button
                        onClick={() => setEditorOpen(true)}
                        style={{
                            display: "flex",
                            alignItems: "center",
                            gap: "0.4rem",
                            background: "rgba(168,85,247,0.07)",
                            border: "none",
                            color: "#A855F7",
                            padding: "0 0.75rem",
                            height: "32px",
                            fontSize: "0.72rem",
                            fontWeight: 800,
                            cursor: "pointer",
                            letterSpacing: "0.04em",
                            whiteSpace: "nowrap"
                        }}
                    >
                        <Settings size={13} />
                    </button>

                    <Link
                        href="/compare"
                        style={{
                            display: "flex",
                            alignItems: "center",
                            gap: "0.4rem",
                            background: "rgba(6,182,212,0.07)",
                            color: "#06B6D4",
                            padding: "0 0.75rem",
                            height: "32px",
                            fontSize: "0.72rem",
                            fontWeight: 800,
                            textDecoration: "none",
                            letterSpacing: "0.04em",
                            whiteSpace: "nowrap"
                        }}
                    >
                        <LayoutGrid size={13} />
                        COMPARE
                    </Link>

                    <button
                        className="btn-primary"
                        onClick={handleRunScan}
                        disabled={isScanning}
                        style={{
                            height: "32px",
                            padding: "0 1rem",
                            whiteSpace: "nowrap",
                            display: "flex",
                            alignItems: "center"
                        }}
                    >
                        {isScanning ? (
                            <>
                                <RefreshCw size={14} style={{ animation: "spin 1s linear infinite" }} />
                                SCANNING...
                            </>
                        ) : (
                            <>
                                <Play size={14} fill="currentColor" />
                                RUN SCAN
                            </>
                        )}
                    </button>
                </div>
            </div>
            {editorOpen && <ScoringEditor onClose={() => setEditorOpen(false)} />}
        </header>
    );
};
