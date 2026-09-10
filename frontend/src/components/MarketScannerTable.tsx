"use client";

import React, { useState } from "react";
import { CandidateRow, pinSymbol, unpinSymbol } from "@/lib/api";
import { ChevronRight, Search, Star } from "lucide-react";

interface MarketScannerTableProps {
    candidates: CandidateRow[];
    onSelectCandidate: (candidate: CandidateRow) => void;
    onPinToggled: () => void;
}

export const MarketScannerTable: React.FC<MarketScannerTableProps> = ({
    candidates,
    onSelectCandidate,
    onPinToggled,
}) => {
    const [activeTab, setActiveTab] = useState<string>("ALL");
    const [searchQuery, setSearchQuery] = useState<string>("");

    const handlePinClick = async (e: React.MouseEvent, c: CandidateRow) => {
        e.stopPropagation();
        try {
            if (c.pinned) {
                await unpinSymbol(c.product_id);
            } else {
                await pinSymbol(c.product_id);
            }
            onPinToggled();
        } catch (err) {
            console.error("Pin toggle failed:", err);
        }
    };

    const formatPrice = (v: number | null | undefined): string => {
        if (v === null || v === undefined) return "-";
        if (v < 0.0001) return `$${v.toFixed(6)}`;
        if (v < 1.0) return `$${v.toFixed(5)}`;
        if (v < 10.0) return `$${v.toFixed(3)}`;
        return `$${v.toFixed(2)}`;
    };

    const formatVol = (v: number | null | undefined): string => {
        if (!v) return "$0";
        if (v >= 1_000_000_000) return `$${(v / 1_000_000_000).toFixed(2)}B`;
        if (v >= 1_000_000) return `$${(v / 1_000_000).toFixed(2)}M`;
        if (v >= 1_000) return `$${(v / 1_000).toFixed(1)}K`;
        return `$${v.toFixed(0)}`;
    };

    const filteredCandidates = candidates.filter((c) => {
        const matchesSearch = c.product_id.toLowerCase().includes(searchQuery.toLowerCase());
        if (!matchesSearch) return false;

        if (activeTab === "ALL") return true;
        if (activeTab === "PINNED") return c.pinned;
        return c.label === activeTab;
    });

    const getScoreColor = (score: number) => {
        if (score >= 75) return "#10B981"; // Emerald
        if (score >= 65) return "#06B6D4"; // Cyan
        if (score >= 50) return "#F59E0B"; // Amber
        return "#64748B"; // Slate
    };

    return (
        <div style={{ display: "flex", flexDirection: "column", gap: "0.85rem" }}>
            {/* Top controls: Filter tabs & Search bar */}
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "1rem" }}>
                <div className="filter-tabs">
                    {["ALL", "ENTRY_ZONE", "COILED", "EARLY", "WATCH", "PINNED"].map((tab) => (
                        <button
                            key={tab}
                            className={`tab-btn ${activeTab === tab ? "active" : ""}`}
                            onClick={() => setActiveTab(tab)}
                        >
                            {tab === "PINNED" ? "📌 PINNED" : tab.replace("_", " ")}
                        </button>
                    ))}
                </div>

                <div style={{ position: "relative", width: "260px" }}>
                    <Search
                        size={15}
                        color="var(--text-dim)"
                        style={{ position: "absolute", left: "0.75rem", top: "50%", transform: "translateY(-50%)" }}
                    />
                    <input
                        type="text"
                        placeholder="Filter ticker (e.g. ZORA, BTC)..."
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                        className="mono"
                        style={{
                            width: "100%",
                            padding: "0.4rem 0.75rem 0.4rem 2.25rem",
                            background: "rgba(11, 15, 25, 0.9)",
                            border: "none",
                            borderRadius: 0,
                            color: "#FFF",
                            fontSize: "0.75rem",
                            outline: "none",
                        }}
                    />
                </div>
            </div>

            {/* High-Density Scanner Table */}
            <div className="scanner-table-container">
                <table className="scanner-table">
                    <thead>
                        <tr>
                            <th style={{ width: "36px", textAlign: "center" }}>Pin</th>
                            <th>Product</th>
                            <th style={{ textAlign: "right" }}>Last Price</th>
                            <th style={{ textAlign: "right" }}>24h %</th>
                            <th style={{ textAlign: "center" }}>Score Gauge</th>
                            <th>Setup Classification</th>
                            <th>PIR Range Gauge</th>
                            <th style={{ textAlign: "right" }}>24h Quote Vol</th>
                            <th style={{ textAlign: "right", color: "#34D399" }}>Tranche A (60%)</th>
                            <th style={{ textAlign: "right", color: "#38BDF8" }}>Tranche B (40%)</th>
                            <th style={{ width: "36px" }}></th>
                        </tr>
                    </thead>
                    <tbody>
                        {filteredCandidates.length === 0 ? (
                            <tr>
                                <td colSpan={11} style={{ textAlign: "center", padding: "3rem", color: "var(--text-dim)" }}>
                                    No setup candidates match current filter. Run a scan or adjust search query.
                                </td>
                            </tr>
                        ) : (
                            filteredCandidates.map((c) => {
                                const scoreColor = getScoreColor(c.composite_score);
                                const isPos = c.day_change_pct >= 0;

                                return (
                                    <tr key={c.product_id} onClick={() => onSelectCandidate(c)}>
                                        <td style={{ textAlign: "center" }} onClick={(e) => handlePinClick(e, c)}>
                                            <Star
                                                size={15}
                                                color={c.pinned ? "#F59E0B" : "var(--text-dim)"}
                                                fill={c.pinned ? "#F59E0B" : "none"}
                                                style={{ cursor: "pointer" }}
                                            />
                                        </td>
                                        <td style={{ fontWeight: 800, color: "#FFFFFF" }}>
                                            <div style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                                                <span>{c.product_id}</span>
                                                {c.pinned && (
                                                    <span className="mono" style={{ fontSize: "0.6rem", background: "rgba(245, 158, 11, 0.2)", color: "#FBBF24", padding: "0.1rem 0.3rem", borderRadius: 0, fontWeight: 800 }}>
                                                        PINNED
                                                    </span>
                                                )}
                                            </div>
                                        </td>
                                        <td className="mono" style={{ textAlign: "right", fontWeight: 700, color: "#FFF" }}>
                                            {formatPrice(c.last_price)}
                                        </td>
                                        <td
                                            className="mono"
                                            style={{
                                                textAlign: "right",
                                                fontWeight: 800,
                                                color: isPos ? "var(--accent-emerald)" : "var(--accent-rose)",
                                            }}
                                        >
                                            {isPos ? `+${c.day_change_pct.toFixed(2)}%` : `${c.day_change_pct.toFixed(2)}%`}
                                        </td>
                                        <td style={{ textAlign: "center" }}>
                                            <div style={{ display: "inline-flex", flexDirection: "column", alignItems: "center", gap: "2px" }}>
                                                <span className="mono" style={{ fontWeight: 800, color: scoreColor, fontSize: "0.85rem" }}>
                                                    {c.composite_score.toFixed(0)}
                                                </span>
                                                <div style={{ width: "36px", height: "3px", background: "rgba(255,255,255,0.08)", borderRadius: 0, overflow: "hidden" }}>
                                                    <div style={{ width: `${Math.min(c.composite_score, 100)}%`, height: "100%", background: scoreColor }} />
                                                </div>
                                            </div>
                                        </td>
                                        <td>
                                            {c.label === "ENTRY_ZONE" && c.ladder ? (
                                                <div style={{ display: "flex", flexDirection: "column", gap: "4px", alignItems: "flex-start" }}>
                                                    <span
                                                        className="label-badge mono"
                                                        style={{
                                                            background: "rgba(16, 185, 129, 0.15)",
                                                            color: "#34D399",
                                                            border: "none",
                                                            boxShadow: "0 0 8px rgba(16,185,129,0.4)"
                                                        }}
                                                    >
                                                        TAGGED @ {formatPrice(c.ladder.tranche_a_price)}
                                                    </span>
                                                    <div className="mono" style={{ fontSize: "0.6rem", display: "flex", gap: "6px" }}>
                                                        <span style={{ color: "#10B981" }}>TP: {formatPrice(c.ladder.target_1_price)}</span>
                                                        <span style={{ color: "#64748B" }}>|</span>
                                                        <span style={{ color: "#F43F5E" }}>SL: {formatPrice(c.ladder.stop_price)}</span>
                                                    </div>
                                                </div>
                                            ) : (
                                                <span className={`label-badge ${c.label}`}>{c.label.replace("_", " ")}</span>
                                            )}
                                        </td>
                                        <td>
                                            <div style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                                                <span className="mono" style={{ fontSize: "0.7rem", color: "var(--text-muted)", width: "30px" }}>
                                                    {c.pos_in_range.toFixed(2)}
                                                </span>
                                                <div className="pir-bar-bg">
                                                    <div
                                                        className="pir-bar-fill"
                                                        style={{
                                                            width: `${Math.min(Math.max(c.pos_in_range * 100, 0), 100)}%`,
                                                            background: c.pos_in_range > 0.8 ? "var(--accent-rose)" : c.pos_in_range >= 0.3 && c.pos_in_range <= 0.65 ? "var(--accent-emerald)" : "var(--accent-blue)",
                                                        }}
                                                    />
                                                </div>
                                            </div>
                                        </td>
                                        <td className="mono" style={{ textAlign: "right", color: "var(--text-muted)", fontSize: "0.75rem" }}>
                                            {formatVol(c.quote_vol_24h)}
                                        </td>
                                        <td className="mono" style={{ textAlign: "right", color: "#34D399", fontWeight: 700 }}>
                                            {c.ladder ? formatPrice(c.ladder.tranche_a_price) : "-"}
                                        </td>
                                        <td className="mono" style={{ textAlign: "right", color: "#38BDF8", fontWeight: 700 }}>
                                            {c.ladder ? formatPrice(c.ladder.tranche_b_price) : "-"}
                                        </td>
                                        <td style={{ textAlign: "center", color: "var(--text-dim)" }}>
                                            <ChevronRight size={16} />
                                        </td>
                                    </tr>
                                );
                            })
                        )}
                    </tbody>
                </table>
            </div>
        </div>
    );
};
