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
        <div style={{
            display: "grid",
            gridTemplateColumns: "220px 1fr",
            gap: "2rem",
            padding: "1rem 0"
        }}>
            {/* LEFT COLUMN: INPUTS */}
            <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>

                <div style={{ display: "flex", width: "100%", border: "1px solid var(--line)" }}>
                    <button
                        onClick={() => setSide("LONG")}
                        style={{
                            flex: 1,
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "center",
                            gap: "0.25rem",
                            padding: "0.35rem 0",
                            background: side === "LONG" ? "var(--bg-pos)" : "transparent",
                            color: side === "LONG" ? "var(--pos)" : "var(--text-4)",
                            border: "none",
                            borderRight: "1px solid var(--line)",
                            fontWeight: 800,
                            fontSize: "0.65rem",
                            cursor: "pointer",
                            transition: "all 0.15s ease",
                        }}
                    >
                        LONG
                    </button>
                    <button
                        onClick={() => setSide("SHORT")}
                        style={{
                            flex: 1,
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "center",
                            gap: "0.25rem",
                            padding: "0.35rem 0",
                            background: side === "SHORT" ? "var(--bg-neg)" : "transparent",
                            color: side === "SHORT" ? "var(--neg)" : "var(--text-4)",
                            border: "none",
                            fontWeight: 800,
                            fontSize: "0.65rem",
                            cursor: "pointer",
                            transition: "all 0.15s ease",
                        }}
                    >
                        SHORT
                    </button>
                </div>

                <div>
                    <label style={{ fontSize: "0.65rem", color: "var(--text-3)", fontWeight: 500, display: "block", marginBottom: "0.4rem" }}>
                        ALLOCATION
                    </label>
                    <div style={{ position: "relative" }}>
                        <DollarSign size={12} color="var(--text-3)" style={{ position: "absolute", left: "0.5rem", top: "50%", transform: "translateY(-50%)" }} />
                        <input
                            type="number"
                            value={accountSize}
                            onChange={(e) => setAccountSize(Math.max(10, Number(e.target.value)))}
                            className="mono"
                            style={{
                                width: "100%",
                                background: "transparent",
                                border: "1px solid var(--line-heavy)",
                                padding: "0.35rem 0.5rem 0.35rem 1.5rem",
                                color: "var(--text-main)",
                                fontSize: "0.8rem",
                                outline: "none",
                            }}
                        />
                    </div>
                </div>

                <div>
                    <label style={{ fontSize: "0.65rem", color: "var(--text-3)", fontWeight: 500, display: "block", marginBottom: "0.4rem" }}>
                        LEVERAGE ({leverage}X)
                    </label>
                    <input
                        type="range"
                        min={1}
                        max={10}
                        step={1}
                        value={leverage}
                        onChange={(e) => setLeverage(Number(e.target.value))}
                        style={{ width: "100%", accentColor: "var(--info)", cursor: "pointer" }}
                    />
                </div>
            </div>

            {/* RIGHT COLUMN: OUTPUTS */}
            <div style={{ display: "flex", flexDirection: "column" }}>

                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", borderBottom: "1px solid var(--line)", paddingBottom: "0.5rem", marginBottom: "0.5rem" }}>
                    <span style={{ fontSize: "0.7rem", color: "var(--text-4)", fontWeight: 500 }}>POSITION EXPOSURE</span>
                    <div style={{ textAlign: "right" }}>
                        <span className="mono" style={{ color: "var(--text-main)", fontSize: "0.85rem", fontWeight: 700 }}>${positionSize.toLocaleString()}</span>
                    </div>
                </div>

                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", borderBottom: "1px solid var(--line)", paddingBottom: "0.5rem", marginBottom: "0.5rem" }}>
                    <span style={{ fontSize: "0.7rem", color: "var(--text-4)", fontWeight: 500 }}>MAX LOSS (SL)</span>
                    <div style={{ textAlign: "right" }}>
                        <span className="mono" style={{ color: "var(--neg-bright)", fontSize: "0.85rem", fontWeight: 700, display: "block" }}>{formatCurr(stopPnL.pnl)}</span>
                        <span className="mono" style={{ color: "var(--neg)", fontSize: "0.65rem" }}>{stopPnL.pct.toFixed(2)}%</span>
                    </div>
                </div>

                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", borderBottom: "1px solid var(--line)", paddingBottom: "0.5rem", marginBottom: "0.5rem" }}>
                    <span style={{ fontSize: "0.7rem", color: "var(--text-4)", fontWeight: 500 }}>TARGET 1</span>
                    <div style={{ textAlign: "right" }}>
                        <span className="mono" style={{ color: "var(--accent-blue-bright)", fontSize: "0.85rem", fontWeight: 700, display: "block" }}>{formatCurr(t1PnL.pnl)}</span>
                        <span className="mono" style={{ color: "var(--accent-blue)", fontSize: "0.65rem" }}>+{t1PnL.pct.toFixed(2)}%</span>
                    </div>
                </div>

                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
                    <span style={{ fontSize: "0.7rem", color: "var(--text-4)", fontWeight: 500 }}>TARGET 2</span>
                    <div style={{ textAlign: "right" }}>
                        <span className="mono" style={{ color: "var(--accent-purple-bright)", fontSize: "0.85rem", fontWeight: 700, display: "block" }}>{formatCurr(t2PnL.pnl)}</span>
                        <span className="mono" style={{ color: "var(--accent-purple)", fontSize: "0.65rem" }}>+{t2PnL.pct.toFixed(2)}%</span>
                    </div>
                </div>

            </div>
        </div>
    );
}
