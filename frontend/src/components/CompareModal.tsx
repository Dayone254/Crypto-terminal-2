import React, { useState, useEffect } from "react";
import { CandidateRow, fetchCandidates } from "@/lib/api";
import { X, Search, Activity, ArrowRightLeft } from "lucide-react";

interface CompareModalProps {
    baseAsset: CandidateRow;
    onClose: () => void;
}

export function CompareModal({ baseAsset, onClose }: CompareModalProps) {
    const [candidates, setCandidates] = useState<CandidateRow[]>([]);
    const [targetSymbol, setTargetSymbol] = useState<string>("");
    const [searchQuery, setSearchQuery] = useState("");
    const [targetAsset, setTargetAsset] = useState<CandidateRow | null>(null);

    useEffect(() => {
        fetchCandidates().then(list => setCandidates(list));
    }, []);

    const handleSelectTarget = (sym: string) => {
        setTargetSymbol(sym);
        const match = candidates.find(c => c.product_id === sym);
        if (match) setTargetAsset(match);
    };

    const formatPrice = (v: number) => {
        if (v < 0.0001) return `$${v.toFixed(6)}`;
        if (v < 1.0) return `$${v.toFixed(5)}`;
        if (v < 10.0) return `$${v.toFixed(3)}`;
        return `$${v.toFixed(2)}`;
    };

    const deltaColor = (val1: number, val2: number) => {
        if (val1 > val2) return "var(--pos)"; // Emerald
        if (val1 < val2) return "var(--neg)"; // Rose
        return "var(--text-muted)";
    };

    const filtered = candidates.filter(
        c => c.product_id !== baseAsset.product_id && c.product_id.toLowerCase().includes(searchQuery.toLowerCase())
    );

    return (
        <div style={{
            position: "fixed",
            top: 0, left: 0, right: 0, bottom: 0,
            background: "rgba(0, 0, 0, 0.8)",
            backdropFilter: "blur(4px)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 9999
        }}>
            <div style={{
                background: "var(--surface-3)", // Tech dark
                border: "none",
                width: "900px",
                maxWidth: "95vw",
                maxHeight: "90vh",
                display: "flex",
                flexDirection: "column",
                boxShadow: "0 20px 40px rgba(0,0,0,0.5)"
            }}>
                {/* Header */}
                <div style={{
                    padding: "1rem 1.5rem",
                    borderBottom: "none",
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    background: "rgba(14, 20, 36, 0.8)"
                }}>
                    <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
                        <ArrowRightLeft size={18} color="var(--accent-cyan)" />
                        <h2 className="mono" style={{ margin: 0, fontSize: "1rem", fontWeight: 800, color: "var(--text-strong)", letterSpacing: "0.05em" }}>
                            CROSS-ASSET BENCHMARKING
                        </h2>
                    </div>
                    <button onClick={onClose} style={{ background: "none", border: "none", color: "var(--text-muted)", cursor: "pointer" }}>
                        <X size={20} />
                    </button>
                </div>

                <div style={{ display: "flex", flex: 1, overflow: "hidden" }}>
                    {/* Left Panel: Search & Selection */}
                    <div style={{
                        width: "250px",
                        borderRight: "none",
                        display: "flex",
                        flexDirection: "column",
                        background: "var(--surface-1)"
                    }}>
                        <div style={{ padding: "1rem", borderBottom: "none" }}>
                            <div style={{
                                position: "relative",
                                display: "flex",
                                alignItems: "center"
                            }}>
                                <Search size={14} style={{ position: "absolute", left: "10px", color: "var(--text-muted)" }} />
                                <input
                                    type="text"
                                    placeholder="Search asset..."
                                    value={searchQuery}
                                    onChange={e => setSearchQuery(e.target.value)}
                                    className="mono"
                                    style={{
                                        width: "100%", padding: "0.5rem 0.5rem 0.5rem 2rem",
                                        background: "rgba(0,0,0,0.4)",
                                        border: "none",
                                        color: "var(--text-strong)",
                                        fontSize: "0.75rem",
                                        outline: "none"
                                    }}
                                />
                            </div>
                        </div>
                        <div style={{ overflowY: "auto", flex: 1 }}>
                            {filtered.map(c => (
                                <button
                                    key={c.product_id}
                                    onClick={() => handleSelectTarget(c.product_id)}
                                    className="mono"
                                    style={{
                                        width: "100%",
                                        textAlign: "left",
                                        padding: "0.75rem 1rem",
                                        background: targetSymbol === c.product_id ? "rgba(6, 182, 212, 0.15)" : "transparent",
                                        border: "none",
                                        borderBottom: "none",
                                        color: targetSymbol === c.product_id ? "var(--accent-cyan)" : "var(--text-main)",
                                        cursor: "pointer",
                                        display: "flex",
                                        justifyContent: "space-between",
                                        alignItems: "center"
                                    }}
                                >
                                    <span style={{ fontWeight: 700 }}>{c.product_id}</span>
                                    <span style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>{c.composite_score.toFixed(0)}</span>
                                </button>
                            ))}
                        </div>
                    </div>

                    {/* Right Panel: Matrix Matrix */}
                    <div style={{ flex: 1, padding: "2rem", overflowY: "auto" }}>
                        {!targetAsset ? (
                            <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", height: "100%", color: "var(--text-muted)", gap: "1rem" }}>
                                <Activity size={32} />
                                <div className="mono" style={{ fontSize: "0.85rem" }}>Select a target asset from the list to benchmark against {baseAsset.product_id}</div>
                            </div>
                        ) : (
                            <div style={{ display: "flex", flexDirection: "column", gap: "2rem" }}>
                                {/* Title Cards */}
                                <div style={{ display: "grid", gridTemplateColumns: "1fr auto 1fr", gap: "2rem", alignItems: "center" }}>
                                    <div style={{ textAlign: "center", padding: "1.5rem", background: "rgba(14, 20, 36, 0.5)", border: "none", width: "100%" }}>
                                        <div style={{ fontSize: "0.7rem", color: "var(--text-dim)", marginBottom: "0.5rem" }}>BASE ASSET</div>
                                        <h3 className="mono" style={{ margin: 0, fontSize: "1.75rem", color: "var(--text-strong)" }}>{baseAsset.product_id}</h3>
                                        <div className="mono" style={{ marginTop: "0.5rem", color: "var(--text-muted)" }}>{formatPrice(baseAsset.last_price)}</div>
                                    </div>
                                    <div style={{ color: "var(--text-dim)", fontWeight: 800 }}>VS</div>
                                    <div style={{ textAlign: "center", padding: "1.5rem", background: "rgba(14, 20, 36, 0.5)", border: "none", width: "100%" }}>
                                        <div style={{ fontSize: "0.7rem", color: "var(--text-dim)", marginBottom: "0.5rem" }}>TARGET ASSET</div>
                                        <h3 className="mono" style={{ margin: 0, fontSize: "1.75rem", color: "var(--text-strong)" }}>{targetAsset.product_id}</h3>
                                        <div className="mono" style={{ marginTop: "0.5rem", color: "var(--text-muted)" }}>{formatPrice(targetAsset.last_price)}</div>
                                    </div>
                                </div>

                                {/* Comparison Table */}
                                <div style={{ border: "none", background: "var(--surface-1)" }}>
                                    <table style={{ width: "100%", borderCollapse: "collapse", textAlign: "left" }} className="mono">
                                        <thead>
                                            <tr style={{ background: "rgba(14, 20, 36, 0.8)", fontSize: "0.7rem", color: "var(--text-dim)", borderBottom: "none" }}>
                                                <th style={{ padding: "0.75rem 1rem" }}>METRIC</th>
                                                <th style={{ padding: "0.75rem 1rem" }}>{baseAsset.product_id}</th>
                                                <th style={{ padding: "0.75rem 1rem" }}>{targetAsset.product_id}</th>
                                                <th style={{ padding: "0.75rem 1rem", textAlign: "right" }}>DELTA</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {/* Composite Score */}
                                            <tr style={{ borderBottom: "none", fontSize: "0.85rem" }}>
                                                <td style={{ padding: "1rem", color: "var(--text-muted)" }}>Composite Quality Score</td>
                                                <td style={{ padding: "1rem", color: "var(--text-strong)" }}>{baseAsset.composite_score.toFixed(1)}</td>
                                                <td style={{ padding: "1rem", color: "var(--text-strong)" }}>{targetAsset.composite_score.toFixed(1)}</td>
                                                <td style={{ padding: "1rem", textAlign: "right", color: deltaColor(baseAsset.composite_score, targetAsset.composite_score) }}>
                                                    {baseAsset.composite_score > targetAsset.composite_score ? "BASE LEADS" : targetAsset.composite_score > baseAsset.composite_score ? "TARGET LEADS" : "EQUAL"}
                                                </td>
                                            </tr>
                                            {/* Trading Label */}
                                            <tr style={{ borderBottom: "none", fontSize: "0.85rem" }}>
                                                <td style={{ padding: "1rem", color: "var(--text-muted)" }}>Pipeline State</td>
                                                <td style={{ padding: "1rem" }}><span className={`label-badge ${baseAsset.label}`}>{baseAsset.label}</span></td>
                                                <td style={{ padding: "1rem" }}><span className={`label-badge ${targetAsset.label}`}>{targetAsset.label}</span></td>
                                                <td style={{ padding: "1rem", textAlign: "right", color: "var(--text-dim)" }}>-</td>
                                            </tr>
                                            {/* 24h Change */}
                                            <tr style={{ borderBottom: "none", fontSize: "0.85rem" }}>
                                                <td style={{ padding: "1rem", color: "var(--text-muted)" }}>24h Net Change</td>
                                                <td style={{ padding: "1rem", color: baseAsset.day_change_pct >= 0 ? "var(--pos)" : "var(--neg)" }}>{baseAsset.day_change_pct.toFixed(2)}%</td>
                                                <td style={{ padding: "1rem", color: targetAsset.day_change_pct >= 0 ? "var(--pos)" : "var(--neg)" }}>{targetAsset.day_change_pct.toFixed(2)}%</td>
                                                <td style={{ padding: "1rem", textAlign: "right", color: deltaColor(baseAsset.day_change_pct, targetAsset.day_change_pct) }}>
                                                    {Math.abs(baseAsset.day_change_pct - targetAsset.day_change_pct).toFixed(2)}% DIFF
                                                </td>
                                            </tr>
                                            {/* 24h Volume */}
                                            <tr style={{ borderBottom: "none", fontSize: "0.85rem" }}>
                                                <td style={{ padding: "1rem", color: "var(--text-muted)" }}>24h Quote Vol</td>
                                                <td style={{ padding: "1rem", color: "var(--text-strong)" }}>${(baseAsset.quote_vol_24h / 1_000_000).toFixed(1)}M</td>
                                                <td style={{ padding: "1rem", color: "var(--text-strong)" }}>${(targetAsset.quote_vol_24h / 1_000_000).toFixed(1)}M</td>
                                                <td style={{ padding: "1rem", textAlign: "right", color: deltaColor(baseAsset.quote_vol_24h, targetAsset.quote_vol_24h) }}>
                                                    {(baseAsset.quote_vol_24h > targetAsset.quote_vol_24h ? (baseAsset.quote_vol_24h / targetAsset.quote_vol_24h) : (targetAsset.quote_vol_24h / baseAsset.quote_vol_24h)).toFixed(1)}x
                                                </td>
                                            </tr>
                                        </tbody>
                                    </table>
                                </div>
                            </div>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
}
