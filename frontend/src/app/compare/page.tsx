"use client";

import React from "react";
import { MultiChartGrid } from "@/components/MultiChartGrid";
import { LayoutGrid, Zap } from "lucide-react";
import Link from "next/link";

export default function ComparePage() {
    return (
        <div style={{ minHeight: "100vh", display: "flex", flexDirection: "column", background: "var(--bg-dark)" }}>
            {/* Minimal Header */}
            <header style={{
                padding: "0.75rem 1.5rem",
                borderBottom: "none",
                background: "var(--surface-3)",
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                flexShrink: 0,
            }}>
                <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
                    <Link href="/" style={{ display: "flex", alignItems: "center", gap: "0.5rem", textDecoration: "none" }}>
                        <div style={{ background: "rgba(6,182,212,0.15)", border: "none", padding: "0.3rem", borderRadius: "6px", display: "flex" }}>
                            <Zap size={16} color="var(--info)" fill="var(--info)" />
                        </div>
                        <span style={{ fontSize: "0.75rem", fontWeight: 800, color: "var(--text-muted)", letterSpacing: "0.05em" }}>
                            TOP PICKER TERMINAL
                        </span>
                    </Link>
                    <span style={{ color: "var(--panel-border)" }}>|</span>
                    <div style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                        <LayoutGrid size={14} color="var(--info)" />
                        <span style={{ fontSize: "0.8rem", fontWeight: 800, color: "var(--text-2)", letterSpacing: "0.03em" }}>
                            MULTI-CHART COMPARE
                        </span>
                    </div>
                </div>

                <Link
                    href="/"
                    style={{
                        background: "rgba(255,255,255,0.04)",
                        border: "none",
                        color: "var(--text-muted)",
                        padding: "0.35rem 0.8rem",
                        borderRadius: "6px",
                        fontSize: "0.72rem",
                        fontWeight: 700,
                        textDecoration: "none",
                        letterSpacing: "0.04em",
                    }}
                >
                    ← SCANNER
                </Link>
            </header>

            {/* Grid Area */}
            <main style={{ flex: 1, padding: "1rem", minHeight: 0, display: "flex", flexDirection: "column" }}>
                <MultiChartGrid />
            </main>
        </div>
    );
}
