"use client";

import React, { useEffect, useState } from "react";
import { Activity, Target, ShieldAlert, TrendingUp, TrendingDown, Clock, Crosshair } from "lucide-react";
import { apiFetch } from "@/lib/api";

interface BacktestStats {
    win_rate: number;
    total_closed: number;
    wins: number;
    losses: number;
    pending_count: number;
    active: any[];
    recent: any[];
}

export const BacktestLedger: React.FC = () => {
    const [stats, setStats] = useState<BacktestStats | null>(null);

    useEffect(() => {
        const fetchStats = async () => {
            try {
                const res = await apiFetch("/api/v1/backtest/stats");
                if (res.ok) {
                    const data = await res.json();
                    setStats(data);
                }
            } catch (err) {
                console.error("Backtest fetch error", err);
            }
        };

        fetchStats();
        // Poll every 30 seconds
        const interval = setInterval(fetchStats, 30000);
        return () => clearInterval(interval);
    }, []);

    if (!stats) return null;

    return (
        <div style={{ background: "var(--surface-3)", borderRadius: 0, border: "none", overflow: "hidden", display: "flex", flexDirection: "column" }}>

            {/* Header */}
            <div style={{ background: "var(--surface-1)", padding: "1rem 1.25rem", borderBottom: "none", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "0.6rem" }}>
                    <Activity size={18} color="var(--accent-cyan)" />
                    <h2 style={{ fontSize: "0.95rem", fontWeight: 800, margin: 0, color: "var(--text-2)", letterSpacing: "0.02em", textTransform: "uppercase" }}>
                        Statistical Edge Tracker
                    </h2>
                </div>
                <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", display: "flex", alignItems: "center", gap: "0.4rem" }}>
                    <Clock size={12} /> Live Engine Active
                </div>
            </div>

            <div style={{ display: "flex", padding: "1.25rem", gap: "1.5rem" }}>

                {/* Win-Rate Ring */}
                <div style={{ flex: "0 0 160px", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" }}>
                    <div style={{ position: "relative", width: "120px", height: "120px" }}>
                        <svg width="120" height="120" viewBox="0 0 120 120">
                            {/* Track */}
                            <circle cx="60" cy="60" r="50" fill="none" stroke="rgba(255,255,255,0.05)" strokeWidth="12" />
                            {/* Fill */}
                            <circle
                                cx="60"
                                cy="60"
                                r="50"
                                fill="none"
                                stroke={stats.win_rate > 50 ? "var(--pos)" : "var(--warn)"}
                                strokeWidth="12"
                                strokeDasharray="314"
                                strokeDashoffset={314 - (314 * stats.win_rate) / 100}
                                strokeLinecap="round"
                                transform="rotate(-90 60 60)"
                                style={{ transition: "stroke-dashoffset 1s ease-out" }}
                            />
                        </svg>
                        <div style={{ position: "absolute", top: 0, left: 0, width: "100%", height: "100%", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" }}>
                            <span className="mono" style={{ fontSize: "1.5rem", fontWeight: 800, color: "var(--text-strong)" }}>{stats.win_rate.toFixed(0)}%</span>
                            <span style={{ fontSize: "0.55rem", color: "var(--text-dim)", textTransform: "uppercase", letterSpacing: "0.05em", fontWeight: 700 }}>Avg Win Rate</span>
                        </div>
                    </div>

                    <div style={{ display: "flex", gap: "1rem", marginTop: "1rem", textAlign: "center" }}>
                        <div>
                            <div style={{ fontSize: "0.65rem", color: "var(--text-dim)", textTransform: "uppercase" }}>Wins</div>
                            <div className="mono" style={{ fontSize: "1rem", fontWeight: 800, color: "var(--pos)" }}>{stats.wins}</div>
                        </div>
                        <div>
                            <div style={{ fontSize: "0.65rem", color: "var(--text-dim)", textTransform: "uppercase" }}>Losses</div>
                            <div className="mono" style={{ fontSize: "1rem", fontWeight: 800, color: "var(--neg)" }}>{stats.losses}</div>
                        </div>
                    </div>
                </div>

                {/* Active Trading Pipeline */}
                <div style={{ flex: "1", display: "flex", flexDirection: "column", gap: "1rem" }}>
                    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                        <span style={{ fontSize: "0.75rem", fontWeight: 800, color: "var(--text-muted)" }}>ACTIVE FORWARD-TESTS ({stats.pending_count})</span>
                    </div>

                    <div style={{ flex: 1, overflowY: "auto", maxHeight: "160px", paddingRight: "0.5rem" }}>
                        {stats.active.length === 0 ? (
                            <div style={{ height: "100%", display: "flex", alignItems: "center", justifyContent: "center", color: "var(--text-dim)", fontSize: "0.8rem", border: "1px dashed rgba(255,255,255,0.05)", borderRadius: 0 }}>
                                No signals in pipeline... waiting for scanner entries.
                            </div>
                        ) : (
                            <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                                {stats.active.map((trade: any) => (
                                    <div key={trade.id} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", background: "rgba(255,255,255,0.02)", border: "none", padding: "0.6rem 0.8rem", borderRadius: 0 }}>
                                        <div style={{ display: "flex", alignItems: "center", gap: "0.8rem" }}>
                                            <div style={{ background: "var(--warn)", color: "var(--text-inverse)", fontSize: "0.65rem", fontWeight: 800, padding: "0.1rem 0.3rem", borderRadius: 0 }}>PENDING</div>
                                            <span style={{ fontWeight: 800, color: "var(--text-strong)", fontSize: "0.85rem" }}>{trade.symbol}</span>
                                        </div>
                                        <div className="mono" style={{ display: "flex", gap: "1rem", fontSize: "0.75rem", color: "var(--text-dim)" }}>
                                            <span><Target size={12} color="var(--pos)" style={{ marginRight: '4px' }} />{trade.tp_price}</span>
                                            <span><Crosshair size={12} color="var(--info)" style={{ marginRight: '4px' }} />{trade.entry_price}</span>
                                            <span><ShieldAlert size={12} color="var(--neg)" style={{ marginRight: '4px' }} />{trade.sl_price}</span>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                </div>
            </div>

        </div>
    );
};
