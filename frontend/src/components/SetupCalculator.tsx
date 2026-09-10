"use client";

import React, { useState } from "react";
import { CandidateLadder } from "@/lib/api";
import { ArrowDownRight, ArrowUpRight, DollarSign, Sliders } from "lucide-react";

interface SetupCalculatorProps {
    symbol: string;
    lastPrice: number;
    ladder: CandidateLadder | null;
}

export function SetupCalculator({ symbol, lastPrice, ladder }: SetupCalculatorProps) {
    const defaultSide = (ladder?.trade_direction === "SHORT") ? "SHORT" : "LONG";
    const [side, setSide] = useState<"LONG" | "SHORT">(defaultSide);

    // Sync side if ladder direction changes (i.e. on load)
    React.useEffect(() => {
        if (ladder?.trade_direction) {
            setSide(ladder.trade_direction as "LONG" | "SHORT");
        }
    }, [ladder?.trade_direction]);
    const [accountSize, setAccountSize] = useState<number>(1000);
    const [leverage, setLeverage] = useState<number>(1);

    const entryA = ladder?.tranche_a_price || lastPrice * 0.99;
    const entryB = ladder?.tranche_b_price || lastPrice * 0.97;
    const stopPrice = ladder?.stop_price || (side === "LONG" ? lastPrice * 0.97 : lastPrice * 1.03);
    const target1 = ladder?.target_1_price || (side === "LONG" ? lastPrice * 1.05 : lastPrice * 0.95);
    const target2 = ladder?.target_2_price || (side === "LONG" ? lastPrice * 1.10 : lastPrice * 0.90);

    const avgEntry = entryA * 0.6 + entryB * 0.4;
    const positionSize = accountSize * leverage;
    const tokenUnits = avgEntry > 0 ? positionSize / avgEntry : 0;

    const calcPnL = (exitPrice: number) => {
        if (side === "LONG") {
            const pct = avgEntry > 0 ? ((exitPrice - avgEntry) / avgEntry) * 100 : 0;
            const pnl = (pct / 100) * positionSize;
            return { pct, pnl };
        } else {
            const pct = avgEntry > 0 ? ((avgEntry - exitPrice) / avgEntry) * 100 : 0;
            const pnl = (pct / 100) * positionSize;
            return { pct, pnl };
        }
    };

    const stopPnL = calcPnL(stopPrice);
    const t1PnL = calcPnL(target1);
    const t2PnL = calcPnL(target2);

    const formatCurr = (val: number) =>
        val >= 0 ? `+$${val.toFixed(2)}` : `-$${Math.abs(val).toFixed(2)}`;

    return (
        <div style={{ background: "#0b0f19", border: "none", borderRadius: 0, padding: "1.25rem", display: "flex", flexDirection: "column", gap: "1rem" }}>
            {/* Header & Side Toggle */}
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", borderBottom: "none", paddingBottom: "0.75rem" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                    <Sliders size={18} color="var(--accent-cyan)" />
                    <span style={{ fontWeight: 800, fontSize: "0.9rem", color: "#FFF" }}>TRADE SETUP CALCULATOR</span>
                </div>

                <div style={{ display: "flex", alignItems: "center", background: "rgba(0,0,0,0.5)", padding: "0.25rem", borderRadius: 0, border: "none" }}>
                    <button
                        onClick={() => setSide("LONG")}
                        style={{
                            display: "flex",
                            alignItems: "center",
                            gap: "0.3rem",
                            padding: "0.35rem 0.85rem",
                            borderRadius: 0,
                            fontWeight: 800,
                            fontSize: "0.75rem",
                            cursor: "pointer",
                            border: "none",
                            background: side === "LONG" ? "var(--accent-emerald)" : "transparent",
                            color: side === "LONG" ? "#000" : "var(--text-muted)",
                            transition: "all 0.15s ease",
                        }}
                    >
                        <ArrowUpRight size={14} /> LONG
                    </button>
                    <button
                        onClick={() => setSide("SHORT")}
                        style={{
                            display: "flex",
                            alignItems: "center",
                            gap: "0.3rem",
                            padding: "0.35rem 0.85rem",
                            borderRadius: 0,
                            fontWeight: 800,
                            fontSize: "0.75rem",
                            cursor: "pointer",
                            border: "none",
                            background: side === "SHORT" ? "var(--accent-rose)" : "transparent",
                            color: side === "SHORT" ? "#FFF" : "var(--text-muted)",
                            transition: "all 0.15s ease",
                        }}
                    >
                        <ArrowDownRight size={14} /> SHORT
                    </button>
                </div>
            </div>

            {/* Inputs: Position Allocation & Leverage */}
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>
                <div>
                    <label style={{ fontSize: "0.7rem", color: "var(--text-dim)", fontWeight: 700, textTransform: "uppercase", display: "block", marginBottom: "0.3rem" }}>
                        Capital Allocation ($)
                    </label>
                    <div style={{ position: "relative" }}>
                        <DollarSign size={14} color="var(--text-dim)" style={{ position: "absolute", left: "0.75rem", top: "50%", transform: "translateY(-50%)" }} />
                        <input
                            type="number"
                            value={accountSize}
                            onChange={(e) => setAccountSize(Math.max(10, Number(e.target.value)))}
                            className="mono"
                            style={{
                                width: "100%",
                                background: "rgba(0,0,0,0.6)",
                                border: "none",
                                borderRadius: 0,
                                padding: "0.45rem 0.75rem 0.45rem 2.25rem",
                                color: "#FFF",
                                fontWeight: 700,
                                fontSize: "0.9rem",
                                outline: "none",
                            }}
                        />
                    </div>
                </div>

                <div>
                    <label style={{ fontSize: "0.7rem", color: "var(--text-dim)", fontWeight: 700, textTransform: "uppercase", display: "block", marginBottom: "0.3rem" }}>
                        Leverage ({leverage}x)
                    </label>
                    <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
                        <input
                            type="range"
                            min={1}
                            max={10}
                            step={1}
                            value={leverage}
                            onChange={(e) => setLeverage(Number(e.target.value))}
                            style={{ width: "100%", accentColor: "var(--accent-cyan)", cursor: "pointer" }}
                        />
                        <span className="mono" style={{ background: "rgba(6,182,212,0.15)", border: "none", color: "var(--accent-cyan)", padding: "0.3rem 0.6rem", borderRadius: 0, fontWeight: 800, fontSize: "0.8rem", minWidth: "40px", textAlign: "center" }}>
                            {leverage}x
                        </span>
                    </div>
                </div>
            </div>

            {/* Position Summary */}
            <div className="mono" style={{ background: "rgba(0,0,0,0.5)", border: "none", borderRadius: 0, padding: "0.6rem 0.85rem", display: "flex", justifyContent: "space-between", fontSize: "0.75rem" }}>
                <span style={{ color: "var(--text-muted)" }}>Total Position Exposure:</span>
                <span style={{ color: "#FFF", fontWeight: 800 }}>${positionSize.toLocaleString()} USD ({tokenUnits.toFixed(2)} {symbol.split("-")[0]})</span>
            </div>

            {/* Dynamic Risk & Reward Output Cards */}
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "0.75rem", textAlign: "center" }}>
                {/* Max Risk (SL) */}
                <div style={{ background: "rgba(239, 68, 68, 0.1)", border: "none", borderRadius: 0, padding: "0.6rem 0.75rem" }}>
                    <span style={{ fontSize: "0.65rem", fontWeight: 800, color: "#F87171", textTransform: "uppercase", display: "block" }}>Max Loss (SL)</span>
                    <span className="mono" style={{ fontSize: "1rem", fontWeight: 800, color: "#F87171", display: "block", marginTop: "0.2rem" }}>
                        {formatCurr(stopPnL.pnl)}
                    </span>
                    <span className="mono" style={{ fontSize: "0.65rem", color: "rgba(248, 113, 113, 0.8)", display: "block" }}>
                        {stopPnL.pct.toFixed(2)}%
                    </span>
                </div>

                {/* Target 1 PnL */}
                <div style={{ background: "rgba(59, 130, 246, 0.1)", border: "none", borderRadius: 0, padding: "0.6rem 0.75rem" }}>
                    <span style={{ fontSize: "0.65rem", fontWeight: 800, color: "#60A5FA", textTransform: "uppercase", display: "block" }}>Target 1 PnL</span>
                    <span className="mono" style={{ fontSize: "1rem", fontWeight: 800, color: "#60A5FA", display: "block", marginTop: "0.2rem" }}>
                        {formatCurr(t1PnL.pnl)}
                    </span>
                    <span className="mono" style={{ fontSize: "0.65rem", color: "rgba(96, 165, 250, 0.8)", display: "block" }}>
                        +{t1PnL.pct.toFixed(2)}%
                    </span>
                </div>

                {/* Target 2 PnL */}
                <div style={{ background: "rgba(139, 92, 246, 0.1)", border: "none", borderRadius: 0, padding: "0.6rem 0.75rem" }}>
                    <span style={{ fontSize: "0.65rem", fontWeight: 800, color: "#C084FC", textTransform: "uppercase", display: "block" }}>Target 2 PnL</span>
                    <span className="mono" style={{ fontSize: "1rem", fontWeight: 800, color: "#C084FC", display: "block", marginTop: "0.2rem" }}>
                        {formatCurr(t2PnL.pnl)}
                    </span>
                    <span className="mono" style={{ fontSize: "0.65rem", color: "rgba(192, 132, 252, 0.8)", display: "block" }}>
                        +{t2PnL.pct.toFixed(2)}%
                    </span>
                </div>
            </div>
        </div>
    );
}
