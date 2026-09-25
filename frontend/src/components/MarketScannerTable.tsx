"use client";

import React from "react";
import { Star, Bolt, ChevronRight, TrendingUp, TrendingDown } from "lucide-react";

export interface Candidate {
    id: string;
    symbol: string;
    sector: string;
    exchange: string;
    price: number;
    priceChange: number;
    change24h: number;
    change1h: number;
    score: number;
    rankTag: "ELITE" | "PRIME" | "ALPHA" | "EARLY" | "ACTIVE" | "CHASE";
    classification: string;
    pir: number;
    pirTag: string;
    quoteVol: number;
    cvd: number;
    trancheA: string;
    trancheB: string;
    pinned?: boolean;
    sparklineData: number[];
}

interface MarketScannerTableProps {
    candidates: Candidate[];
    onSelectCandidate?: (candidate: Candidate) => void;
    onPinCandidate?: (symbol: string) => void;
    onFastStageOrder?: (candidate: Candidate) => void;
}

export const MarketScannerTable: React.FC<MarketScannerTableProps> = ({
    candidates,
    onSelectCandidate,
    onPinCandidate,
    onFastStageOrder,
}) => {
    // Format helpers
    const fmtPrice = (p: number) =>
        p >= 100
            ? p.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })
            : p >= 1
                ? p.toFixed(4)
                : p.toFixed(5);

    const fmtVol = (v: number) =>
        v >= 1e6 ? `$${(v / 1e6).toFixed(2)}M` : v >= 1e3 ? `$${(v / 1e3).toFixed(1)}K` : `$${v.toFixed(0)}`;

    const fmtCvd = (c: number) =>
        c > 0 ? `+$${(c / 1e6).toFixed(2)}M CVD` : `-$${(Math.abs(c) / 1e6).toFixed(2)}M CVD`;

    return (
        <div
            style={{
                backgroundColor: "var(--surface-container-low)",
                borderRadius: "6px",
                overflow: "hidden",
                boxShadow: "0 4px 12px rgba(0,0,0,0.3)",
                display: "flex",
                flexDirection: "column",
                border: "1px solid var(--outline-variant)",
            }}
        >
            <div style={{ overflowX: "auto", width: "100%" }}>
                <table style={{ width: "100%", borderCollapse: "collapse", textAlign: "left", userSelect: "none" }}>
                    <thead
                        className="font-label-caps"
                        style={{
                            backgroundColor: "var(--surface-container-lowest)",
                            color: "var(--outline)",
                            letterSpacing: "0.05em",
                            position: "sticky",
                            top: 0,
                            zIndex: 20,
                            borderBottom: "1px solid var(--outline-variant)",
                        }}
                    >
                        <tr>
                            <th style={{ padding: "0.6rem 0.5rem", width: "32px", textAlign: "center" }}>PIN</th>
                            <th style={{ padding: "0.6rem 0.75rem", minWidth: "130px" }}>ASSET / SECTOR</th>
                            <th style={{ padding: "0.6rem 0.75rem", textAlign: "right", minWidth: "95px" }}>LAST PRICE</th>
                            <th style={{ padding: "0.6rem 0.75rem", textAlign: "right", minWidth: "100px" }}>24H / 1H CHG</th>
                            <th style={{ padding: "0.6rem 0.75rem", textAlign: "center", minWidth: "100px" }}>24H TAPE &amp; CVD</th>
                            <th style={{ padding: "0.6rem 0.75rem", textAlign: "center", minWidth: "110px" }}>QUANT SCORE</th>
                            <th style={{ padding: "0.6rem 0.75rem", textAlign: "center", minWidth: "140px" }}>SETUP CLASSIFICATION</th>
                            <th style={{ padding: "0.6rem 0.75rem", textAlign: "center", minWidth: "100px" }}>PIR GAUGE</th>
                            <th style={{ padding: "0.6rem 0.75rem", textAlign: "right", minWidth: "100px" }}>24H VOL / CVD</th>
                            <th style={{ padding: "0.6rem 0.75rem", textAlign: "center", minWidth: "150px" }}>INSTITUTIONAL TRANCHES</th>
                            <th style={{ padding: "0.6rem 0.5rem", textAlign: "right", width: "64px" }}>ACT</th>
                        </tr>
                    </thead>
                    <tbody className="font-body-sm" style={{ color: "var(--on-surface)" }}>
                        {candidates.map((c, idx) => {
                            const isPositive = c.change24h >= 0;
                            const isHighConviction = c.score >= 95;

                            return (
                                <tr
                                    key={c.id || c.symbol}
                                    style={{
                                        borderBottom: "1px solid rgba(255,255,255,0.03)",
                                        backgroundColor: isHighConviction ? "rgba(0, 245, 155, 0.03)" : idx % 2 === 1 ? "rgba(255,255,255,0.01)" : "transparent",
                                        transition: "background-color var(--dur-fast) var(--ease-out)",
                                        cursor: "pointer",
                                    }}
                                    onMouseEnter={(e) => {
                                        e.currentTarget.style.backgroundColor = "var(--surface-container)";
                                    }}
                                    onMouseLeave={(e) => {
                                        e.currentTarget.style.backgroundColor = isHighConviction
                                            ? "rgba(0, 245, 155, 0.03)"
                                            : idx % 2 === 1
                                                ? "rgba(255,255,255,0.01)"
                                                : "transparent";
                                    }}
                                    onClick={() => onSelectCandidate?.(c)}
                                >
                                    {/* PIN */}
                                    <td style={{ padding: "0.5rem", textAlign: "center" }}>
                                        <button
                                            onClick={(e) => {
                                                e.stopPropagation();
                                                onPinCandidate?.(c.symbol);
                                            }}
                                            style={{
                                                background: "none",
                                                border: "none",
                                                cursor: "pointer",
                                                color: c.pinned ? "var(--primary-fixed-dim)" : "var(--outline)",
                                                opacity: c.pinned ? 1 : 0.6,
                                            }}
                                        >
                                            <Star size={15} fill={c.pinned ? "var(--primary-fixed-dim)" : "none"} />
                                        </button>
                                    </td>

                                    {/* ASSET / SECTOR */}
                                    <td style={{ padding: "0.5rem 0.75rem" }}>
                                        <div style={{ display: "flex", alignItems: "center", gap: "0.35rem" }}>
                                            <span
                                                className="font-mono-data-primary"
                                                style={{ fontWeight: 700, color: isHighConviction ? "var(--primary)" : "var(--on-surface)" }}
                                            >
                                                {c.symbol}
                                            </span>
                                            <span
                                                className="font-label-caps"
                                                style={{
                                                    fontSize: "9px",
                                                    padding: "0.05rem 0.35rem",
                                                    borderRadius: "3px",
                                                    backgroundColor: "var(--surface-container-high)",
                                                    color: "var(--on-surface-variant)",
                                                }}
                                            >
                                                {c.sector}
                                            </span>
                                        </div>
                                        <span className="font-mono-data-compact" style={{ color: "var(--outline)" }}>
                                            {c.exchange}
                                        </span>
                                    </td>

                                    {/* LAST PRICE */}
                                    <td style={{ padding: "0.5rem 0.75rem", textAlign: "right" }}>
                                        <span className="font-mono-data-primary" style={{ fontWeight: 700, color: "var(--on-surface)" }}>
                                            ${fmtPrice(c.price)}
                                        </span>
                                        <div
                                            className="font-mono-data-compact"
                                            style={{ color: isPositive ? "var(--primary-fixed-dim)" : "var(--secondary)" }}
                                        >
                                            {isPositive ? "▲ +" : "▼ -"}${Math.abs(c.priceChange).toFixed(c.price < 1 ? 5 : 2)}
                                        </div>
                                    </td>

                                    {/* 24H / 1H CHG */}
                                    <td style={{ padding: "0.5rem 0.75rem", textAlign: "right" }}>
                                        <div style={{ display: "inline-flex", flexDirection: "column", alignItems: "flex-end" }}>
                                            <span
                                                className="font-mono-data-compact"
                                                style={{
                                                    padding: "0.1rem 0.35rem",
                                                    borderRadius: "3px",
                                                    fontWeight: 700,
                                                    backgroundColor: isPositive ? "rgba(0, 245, 155, 0.15)" : "rgba(255, 178, 183, 0.15)",
                                                    color: isPositive ? "var(--primary)" : "var(--secondary)",
                                                }}
                                            >
                                                {isPositive ? "+" : ""}{c.change24h.toFixed(2)}%
                                            </span>
                                            <span
                                                className="font-mono-data-compact"
                                                style={{
                                                    fontSize: "10px",
                                                    color: c.change1h >= 0 ? "var(--primary-fixed-dim)" : "var(--secondary)",
                                                }}
                                            >
                                                {c.change1h >= 0 ? "+" : ""}{c.change1h.toFixed(2)}% 1H
                                            </span>
                                        </div>
                                    </td>

                                    {/* 24H TAPE & CVD Sparkline */}
                                    <td style={{ padding: "0.5rem 0.75rem", textAlign: "center" }}>
                                        <div style={{ width: "80px", height: "20px", margin: "0 auto", display: "flex", alignItems: "center" }}>
                                            <svg viewBox="0 0 80 20" style={{ width: "100%", height: "100%", overflow: "visible" }}>
                                                <path
                                                    d={isPositive ? "M0,16 Q20,18 40,8 T80,3" : "M0,4 Q20,2 40,12 T80,18"}
                                                    fill="none"
                                                    stroke={isPositive ? "#00e38f" : "#ffb2b7"}
                                                    strokeWidth="1.5"
                                                    strokeLinecap="round"
                                                />
                                                <path
                                                    d={isPositive ? "M0,18 L25,16 L50,14 L80,7" : "M0,6 L30,10 L50,15 L80,19"}
                                                    fill="none"
                                                    opacity="0.6"
                                                    stroke={isPositive ? "#53ffab" : "#b50036"}
                                                    strokeDasharray="2 2"
                                                    strokeWidth="1"
                                                />
                                            </svg>
                                        </div>
                                    </td>

                                    {/* QUANT SCORE */}
                                    <td style={{ padding: "0.5rem 0.75rem", textAlign: "center" }}>
                                        <div style={{ display: "flex", flexDirection: "column", alignItems: "center" }}>
                                            <div style={{ display: "flex", alignItems: "center", gap: "0.25rem" }}>
                                                <span
                                                    className="font-mono-metric-lg"
                                                    style={{ color: "var(--primary-fixed-dim)", fontWeight: 700 }}
                                                >
                                                    {c.score}
                                                </span>
                                                <span
                                                    className="font-label-caps"
                                                    style={{
                                                        fontSize: "9px",
                                                        padding: "0.05rem 0.25rem",
                                                        borderRadius: "3px",
                                                        backgroundColor: "rgba(0, 245, 155, 0.15)",
                                                        color: "var(--primary)",
                                                    }}
                                                >
                                                    {c.rankTag}
                                                </span>
                                            </div>
                                            <div
                                                style={{
                                                    width: "64px",
                                                    height: "4px",
                                                    backgroundColor: "var(--surface-container-highest)",
                                                    borderRadius: "999px",
                                                    overflow: "hidden",
                                                    marginTop: "0.15rem",
                                                }}
                                            >
                                                <div
                                                    style={{
                                                        height: "100%",
                                                        width: `${c.score}%`,
                                                        backgroundColor: "var(--primary-fixed-dim)",
                                                        borderRadius: "999px",
                                                    }}
                                                />
                                            </div>
                                        </div>
                                    </td>

                                    {/* SETUP CLASSIFICATION */}
                                    <td style={{ padding: "0.5rem 0.75rem", textAlign: "center" }}>
                                        <span
                                            className="font-label-caps"
                                            style={{
                                                padding: "0.2rem 0.5rem",
                                                borderRadius: "4px",
                                                backgroundColor: c.classification.includes("BREAKOUT") || c.classification.includes("SQUEEZE")
                                                    ? "rgba(0, 245, 155, 0.15)"
                                                    : c.classification.includes("MOMENTUM")
                                                        ? "rgba(192, 193, 255, 0.15)"
                                                        : "var(--surface-container-high)",
                                                color: c.classification.includes("BREAKOUT") || c.classification.includes("SQUEEZE")
                                                    ? "var(--primary-fixed-dim)"
                                                    : c.classification.includes("MOMENTUM")
                                                        ? "var(--tertiary-fixed-dim)"
                                                        : "var(--on-surface-variant)",
                                                fontWeight: 600,
                                            }}
                                        >
                                            {c.classification}
                                        </span>
                                    </td>

                                    {/* PIR GAUGE */}
                                    <td style={{ padding: "0.5rem 0.75rem" }}>
                                        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: "0.15rem" }}>
                                            <div
                                                className="font-mono-data-compact"
                                                style={{
                                                    display: "flex",
                                                    justifyContent: "space-between",
                                                    width: "64px",
                                                    fontSize: "10px",
                                                    color: "var(--on-surface-variant)",
                                                }}
                                            >
                                                <span>{c.pir.toFixed(2)}</span>
                                                <span style={{ color: "var(--primary-fixed-dim)" }}>{c.pirTag}</span>
                                            </div>
                                            <div
                                                style={{
                                                    width: "64px",
                                                    height: "6px",
                                                    backgroundColor: "var(--surface-container)",
                                                    borderRadius: "999px",
                                                    position: "relative",
                                                    overflow: "hidden",
                                                }}
                                            >
                                                <div
                                                    style={{
                                                        position: "absolute",
                                                        left: 0,
                                                        top: 0,
                                                        bottom: 0,
                                                        width: `${Math.min(100, c.pir * 100)}%`,
                                                        backgroundColor: c.pir >= 0.7 ? "var(--primary-fixed-dim)" : "var(--secondary)",
                                                        borderRadius: "999px",
                                                    }}
                                                />
                                            </div>
                                        </div>
                                    </td>

                                    {/* 24H VOL / CVD */}
                                    <td style={{ padding: "0.5rem 0.75rem", textAlign: "right" }}>
                                        <div className="font-mono-data-primary" style={{ fontWeight: 600, color: "var(--on-surface)" }}>
                                            {fmtVol(c.quoteVol)}
                                        </div>
                                        <div
                                            className="font-mono-data-compact"
                                            style={{ color: c.cvd >= 0 ? "var(--primary)" : "var(--secondary)", fontWeight: 500 }}
                                        >
                                            {fmtCvd(c.cvd)}
                                        </div>
                                    </td>

                                    {/* INSTITUTIONAL TRANCHES */}
                                    <td style={{ padding: "0.5rem 0.75rem", textAlign: "center" }}>
                                        <div
                                            className="font-mono-data-compact"
                                            style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: "0.35rem" }}
                                        >
                                            <span
                                                style={{
                                                    padding: "0.15rem 0.4rem",
                                                    backgroundColor: "var(--surface-container-high)",
                                                    borderRadius: "3px",
                                                    color: "var(--primary-fixed-dim)",
                                                }}
                                            >
                                                {c.trancheA}
                                            </span>
                                            <span
                                                style={{
                                                    padding: "0.15rem 0.4rem",
                                                    backgroundColor: "var(--surface-container)",
                                                    borderRadius: "3px",
                                                    color: "var(--outline)",
                                                }}
                                            >
                                                {c.trancheB}
                                            </span>
                                        </div>
                                    </td>

                                    {/* ACT */}
                                    <td style={{ padding: "0.5rem", textAlign: "right" }}>
                                        <div style={{ display: "flex", alignItems: "center", justifyContent: "flex-end", gap: "0.25rem" }}>
                                            <button
                                                onClick={(e) => {
                                                    e.stopPropagation();
                                                    onFastStageOrder?.(c);
                                                }}
                                                style={{
                                                    padding: "0.3rem",
                                                    borderRadius: "4px",
                                                    backgroundColor: "var(--primary-container)",
                                                    color: "var(--on-primary-container)",
                                                    border: "none",
                                                    cursor: "pointer",
                                                    display: "flex",
                                                    alignItems: "center",
                                                    justifyContent: "center",
                                                }}
                                                title="Fast Stage Order"
                                            >
                                                <Bolt size={14} fill="currentColor" />
                                            </button>
                                            <button
                                                style={{
                                                    padding: "0.3rem",
                                                    borderRadius: "4px",
                                                    backgroundColor: "transparent",
                                                    color: "var(--on-surface-variant)",
                                                    border: "none",
                                                    cursor: "pointer",
                                                }}
                                            >
                                                <ChevronRight size={14} />
                                            </button>
                                        </div>
                                    </td>
                                </tr>
                            );
                        })}
                    </tbody>
                </table>
            </div>

            {/* ── Table Micro Status Footer ── */}
            <div
                className="font-mono-data-compact"
                style={{
                    padding: "0.4rem 0.75rem",
                    backgroundColor: "var(--surface-container-lowest)",
                    borderTop: "1px solid var(--outline-variant)",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    color: "var(--on-surface-variant)",
                }}
            >
                <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
                    <span>ROWS DISPLAYED: <strong style={{ color: "var(--on-surface)" }}>{candidates.length} OF 512</strong></span>
                    <span>SORT: <strong style={{ color: "var(--primary-fixed-dim)" }}>QUANT SCORE (DESC)</strong></span>
                    <span>DATA FEED: <strong style={{ color: "var(--primary-fixed-dim)" }}>BINANCE / BYBIT / DYDX V4 COMPOSITE</strong></span>
                </div>

                <div style={{ display: "flex", alignItems: "center", gap: "0.35rem" }}>
                    <button
                        style={{
                            padding: "0.15rem 0.5rem",
                            borderRadius: "3px",
                            backgroundColor: "var(--surface-container)",
                            border: "none",
                            color: "var(--outline)",
                            cursor: "pointer",
                        }}
                    >
                        PREV
                    </button>
                    <span style={{ padding: "0 0.35rem", color: "var(--primary)", fontWeight: 700 }}>1</span>
                    <button
                        style={{
                            padding: "0.15rem 0.5rem",
                            borderRadius: "3px",
                            backgroundColor: "var(--surface-container)",
                            border: "none",
                            color: "var(--outline)",
                            cursor: "pointer",
                        }}
                    >
                        NEXT
                    </button>
                </div>
            </div>
        </div>
    );
};
