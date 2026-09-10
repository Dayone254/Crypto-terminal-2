"use client";

import React, { useEffect, useState } from "react";
import { NativeChart } from "@/components/NativeChart";
import { X, LayoutGrid, Search } from "lucide-react";
import { fetchCandidates, CandidateRow } from "@/lib/api";

const DEFAULT_SYMBOLS = ["BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD"];

interface PanelConfig {
    symbol: string;
    entry?: number;
    tp?: number;
    sl?: number;
}

interface SymbolPickerProps {
    current: string;
    candidates: CandidateRow[];
    onChange: (sym: string) => void;
    onClose: () => void;
}

const SymbolPicker: React.FC<SymbolPickerProps> = ({ current, candidates, onChange, onClose }) => {
    const [query, setQuery] = useState("");
    const filtered = candidates.filter(c =>
        c.product_id.toLowerCase().includes(query.toLowerCase())
    ).slice(0, 20);

    return (
        <div style={{
            position: "absolute", top: "3rem", left: "0.5rem", zIndex: 100,
            background: "#0B0F19", border: "none",
            borderRadius: 0, padding: "0.75rem", width: "220px",
            boxShadow: "0 20px 40px rgba(0,0,0,0.7)",
        }}>
            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.5rem", background: "rgba(255,255,255,0.04)", border: "none", borderRadius: 0, padding: "0.4rem 0.6rem" }}>
                <Search size={12} color="var(--text-dim)" />
                <input
                    autoFocus
                    value={query}
                    onChange={e => setQuery(e.target.value)}
                    placeholder="Search symbol..."
                    style={{ background: "transparent", border: "none", outline: "none", color: "#E2E8F0", fontSize: "0.8rem", flex: 1 }}
                />
            </div>
            <div style={{ maxHeight: "220px", overflowY: "auto", display: "flex", flexDirection: "column", gap: "2px" }}>
                {filtered.map(c => (
                    <button
                        key={c.product_id}
                        onClick={() => { onChange(c.product_id); onClose(); }}
                        style={{
                            background: c.product_id === current ? "rgba(6,182,212,0.1)" : "transparent",
                            border: "none", color: c.product_id === current ? "#06B6D4" : "#E2E8F0",
                            padding: "0.4rem 0.5rem", borderRadius: 0, textAlign: "left",
                            cursor: "pointer", fontSize: "0.78rem", fontWeight: 700,
                            display: "flex", justifyContent: "space-between", alignItems: "center",
                        }}
                    >
                        <span>{c.product_id}</span>
                        <span style={{ fontSize: "0.65rem", color: "var(--text-dim)", fontWeight: 400 }}>
                            {c.composite_score?.toFixed(0)}
                        </span>
                    </button>
                ))}
            </div>
        </div>
    );
};

interface ChartPanelProps {
    panel: PanelConfig;
    index: number;
    candidates: CandidateRow[];
    onSymbolChange: (i: number, sym: string) => void;
}

const ChartPanel: React.FC<ChartPanelProps> = ({ panel, index, candidates, onSymbolChange }) => {
    const [pickerOpen, setPickerOpen] = useState(false);

    const candidate = candidates.find(c => c.product_id === panel.symbol);

    return (
        <div style={{ position: "relative", display: "flex", flexDirection: "column", minHeight: 0 }}>
            {/* Panel Header */}
            <div style={{
                display: "flex", alignItems: "center", justifyContent: "space-between",
                padding: "0.6rem 0.75rem", background: "#0B0F19",
                borderBottom: "none",
                borderTopLeftRadius: 0, borderTopRightRadius: 0,
                flexShrink: 0,
            }}>
                <button
                    onClick={() => setPickerOpen(v => !v)}
                    style={{
                        background: "rgba(255,255,255,0.04)", border: "none",
                        color: "#E2E8F0", padding: "0.25rem 0.6rem", borderRadius: 0,
                        cursor: "pointer", fontWeight: 800, fontSize: "0.8rem", display: "flex", alignItems: "center", gap: "0.4rem",
                    }}
                >
                    {panel.symbol}
                    <span style={{ fontSize: "0.6rem", color: "var(--text-dim)" }}>▼</span>
                </button>

                {candidate && (
                    <div style={{ display: "flex", gap: "0.6rem", fontSize: "0.65rem" }}>
                        <span style={{ color: "var(--text-dim)" }}>SCORE</span>
                        <span style={{ color: "#06B6D4", fontWeight: 800 }}>{candidate.composite_score?.toFixed(0)}</span>
                        <span style={{
                            background: candidate.label === "ENTRY_ZONE" ? "rgba(16,185,129,0.2)" : "rgba(6,182,212,0.1)",
                            color: candidate.label === "ENTRY_ZONE" ? "#10B981" : "#06B6D4",
                            padding: "0.1rem 0.4rem", borderRadius: 0, fontWeight: 800,
                        }}>
                            {candidate.label}
                        </span>
                    </div>
                )}
            </div>

            {/* Symbol Picker Dropdown */}
            {pickerOpen && (
                <SymbolPicker
                    current={panel.symbol}
                    candidates={candidates}
                    onChange={(sym) => onSymbolChange(index, sym)}
                    onClose={() => setPickerOpen(false)}
                />
            )}

            {/* Chart */}
            <div style={{ flex: 1, minHeight: 0 }}>
                <NativeChart
                    productId={panel.symbol}
                    entryLevel={candidate?.ladder?.tranche_a_price}
                    tpLevel={candidate?.ladder?.target_1_price}
                    slLevel={candidate?.ladder?.stop_price}
                    height="100%"
                />
            </div>
        </div>
    );
};

export const MultiChartGrid: React.FC = () => {
    const [panels, setPanels] = useState<PanelConfig[]>(
        DEFAULT_SYMBOLS.map(sym => ({ symbol: sym }))
    );
    const [candidates, setCandidates] = useState<CandidateRow[]>([]);

    useEffect(() => {
        fetchCandidates().then(data => {
            setCandidates(data);
            // Auto-populate panels with top candidates if available
            if (data.length >= 4) {
                setPanels(data.slice(0, 4).map(c => ({
                    symbol: c.product_id,
                    entry: c.ladder?.tranche_a_price,
                    tp: c.ladder?.target_1_price,
                    sl: c.ladder?.stop_price,
                })));
            }
        }).catch(() => { });
    }, []);

    const handleSymbolChange = (index: number, sym: string) => {
        const candidate = candidates.find(c => c.product_id === sym);
        setPanels(prev => prev.map((p, i) => i === index ? {
            symbol: sym,
            entry: candidate?.ladder?.tranche_a_price,
            tp: candidate?.ladder?.target_1_price,
            sl: candidate?.ladder?.stop_price,
        } : p));
    };

    return (
        <div style={{ height: "100%", display: "flex", flexDirection: "column", minHeight: 0 }}>
            <div style={{
                display: "grid",
                gridTemplateColumns: "1fr 1fr",
                gridTemplateRows: "1fr 1fr",
                gap: "1rem",
                flex: 1,
                minHeight: 0,
            }}>
                {panels.map((panel, i) => (
                    <div key={i} style={{ border: "none", borderRadius: 0, overflow: "hidden", display: "flex", flexDirection: "column", minHeight: 0 }}>
                        <ChartPanel
                            panel={panel}
                            index={i}
                            candidates={candidates}
                            onSymbolChange={handleSymbolChange}
                        />
                    </div>
                ))}
            </div>
        </div>
    );
};
