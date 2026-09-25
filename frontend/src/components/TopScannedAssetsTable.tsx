"use client";

import React from "react";
import Link from "next/link";
import { CandidateRow } from "@/lib/api";
import { ArrowRight, Star } from "lucide-react";

interface TopScannedAssetsTableProps {
    candidates: CandidateRow[];
    currentSymbol: string;
    onSelectSymbol?: (symbol: string) => void;
}

export const TopScannedAssetsTable: React.FC<TopScannedAssetsTableProps> = ({
    candidates,
    currentSymbol,
}) => {
    // Sort top 5 candidates by score
    const topAssets = React.useMemo(() => {
        return [...candidates]
            .sort((a, b) => b.composite_score - a.composite_score)
            .slice(0, 5);
    }, [candidates]);

    const formatPrice = (v: number | null | undefined): string => {
        if (v === null || v === undefined) return "—";
        if (v < 0.0001) return `$${v.toFixed(6)}`;
        if (v < 1.0) return `$${v.toFixed(4)}`;
        if (v < 10.0) return `$${v.toFixed(3)}`;
        return `$${v.toFixed(2)}`;
    };

    return (
        <div style={{ background: "var(--panel-bg)", border: "1px solid rgba(255,255,255,0.06)", borderRadius: "4px", padding: "1rem", display: "flex", flexDirection: "column", gap: "0.75rem" }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                    <span style={{ fontSize: "0.75rem", fontWeight: 800, color: "var(--text-4)", letterSpacing: "0.05em", textTransform: "uppercase" }}>
                        TOP SCANNED ASSETS
                    </span>
                </div>
                <Link
                    href="/"
                    style={{
                        display: "inline-flex",
                        alignItems: "center",
                        gap: "0.3rem",
                        fontSize: "0.7rem",
                        fontWeight: 700,
                        color: "var(--info)",
                        textDecoration: "none",
                    }}
                >
                    View All <ArrowRight size={12} />
                </Link>
            </div>

            <div style={{ overflowX: "auto" }}>
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.75rem", fontFamily: "var(--font-jetbrains)" }}>
                    <thead>
                        <tr style={{ borderBottom: "1px solid rgba(255,255,255,0.08)", color: "var(--text-4)", textAlign: "left" }}>
                            <th style={{ padding: "0.5rem 0.6rem", fontWeight: 800, width: "60px" }}>RANK</th>
                            <th style={{ padding: "0.5rem 0.6rem", fontWeight: 800 }}>PAIR</th>
                            <th style={{ padding: "0.5rem 0.6rem", fontWeight: 800, textAlign: "right" }}>PRICE</th>
                            <th style={{ padding: "0.5rem 0.6rem", fontWeight: 800, textAlign: "right" }}>24H %</th>
                            <th style={{ padding: "0.5rem 0.6rem", fontWeight: 800, textAlign: "center" }}>SCORE</th>
                            <th style={{ padding: "0.5rem 0.6rem", fontWeight: 800, textAlign: "center" }}>SETUP</th>
                            <th style={{ padding: "0.5rem 0.6rem", fontWeight: 800, textAlign: "right" }}>VOL (24H)</th>
                            <th style={{ padding: "0.5rem 0.6rem", fontWeight: 800, textAlign: "right" }}>OI (24H)</th>
                            <th style={{ padding: "0.5rem 0.6rem", fontWeight: 800, textAlign: "right" }}>FUNDING</th>
                        </tr>
                    </thead>
                    <tbody>
                        {topAssets.map((asset, idx) => {
                            const isSelected = asset.product_id.toLowerCase() === currentSymbol.toLowerCase();
                            const isShort = asset.trade_direction === "SHORT";
                            const symBase = asset.product_id.split("-")[0];

                            return (
                                <tr
                                    key={asset.product_id}
                                    style={{
                                        borderBottom: "1px solid rgba(255,255,255,0.04)",
                                        background: isSelected ? "rgba(6, 182, 212, 0.08)" : "transparent",
                                        transition: "background 0.15s ease",
                                        cursor: "pointer",
                                    }}
                                >
                                    <td style={{ padding: "0.6rem", fontWeight: 800, color: isSelected ? "var(--info)" : "var(--text-3)" }}>
                                        {idx + 1} {isSelected && <span style={{ color: "var(--info)", fontSize: "0.65rem" }}>⟁</span>}
                                    </td>

                                    <td style={{ padding: "0.6rem" }}>
                                        <Link
                                            href={`/market/${asset.product_id}`}
                                            style={{
                                                display: "inline-flex",
                                                alignItems: "center",
                                                gap: "0.5rem",
                                                textDecoration: "none",
                                                color: isSelected ? "var(--info)" : "var(--text-main)",
                                                fontWeight: 800,
                                            }}
                                        >
                                            <div style={{
                                                width: "20px", height: "20px", borderRadius: "50%",
                                                background: "rgba(6, 182, 212, 0.15)", border: "1px solid rgba(6, 182, 212, 0.4)",
                                                display: "flex", alignItems: "center", justifyContent: "center",
                                                fontSize: "0.6rem", fontWeight: 900, color: "var(--info)"
                                            }}>
                                                {symBase.slice(0, 1)}
                                            </div>
                                            {asset.product_id}
                                        </Link>
                                    </td>

                                    <td style={{ padding: "0.6rem", textAlign: "right", fontWeight: 700, color: "var(--text-main)" }}>
                                        {formatPrice(asset.last_price)}
                                    </td>

                                    <td style={{ padding: "0.6rem", textAlign: "right", fontWeight: 700, color: asset.day_change_pct >= 0 ? "var(--pos)" : "var(--neg-bright)" }}>
                                        {asset.day_change_pct >= 0 ? `+${asset.day_change_pct.toFixed(2)}%` : `${asset.day_change_pct.toFixed(2)}%`}
                                    </td>

                                    <td style={{ padding: "0.6rem", textAlign: "center" }}>
                                        <span style={{
                                            fontWeight: 800,
                                            color: "var(--info)",
                                            background: "rgba(6, 182, 212, 0.15)",
                                            padding: "0.15rem 0.45rem",
                                            borderRadius: "2px",
                                            fontSize: "0.72rem"
                                        }}>
                                            {asset.composite_score.toFixed(0)}
                                        </span>
                                    </td>

                                    <td style={{ padding: "0.6rem", textAlign: "center" }}>
                                        <span style={{
                                            fontWeight: 800,
                                            color: isShort ? "var(--neg-bright)" : "var(--pos)",
                                            background: isShort ? "rgba(244, 63, 94, 0.15)" : "rgba(16, 185, 129, 0.15)",
                                            border: isShort ? "1px solid rgba(244, 63, 94, 0.3)" : "1px solid rgba(16, 185, 129, 0.3)",
                                            padding: "0.15rem 0.45rem",
                                            borderRadius: "2px",
                                            fontSize: "0.65rem"
                                        }}>
                                            {isShort ? "SHORT" : "LONG"}
                                        </span>
                                    </td>

                                    <td style={{ padding: "0.6rem", textAlign: "right", color: "var(--text-3)" }}>
                                        ${(asset.quote_vol_24h / 1_000_000).toFixed(2)}M
                                    </td>

                                    <td style={{ padding: "0.6rem", textAlign: "right", color: "var(--text-3)" }}>
                                        —
                                    </td>

                                    <td style={{ padding: "0.6rem", textAlign: "right", color: "var(--pos)", fontWeight: 700 }}>
                                        —
                                    </td>
                                </tr>
                            );
                        })}
                    </tbody>
                </table>
            </div>
        </div>
    );
};
