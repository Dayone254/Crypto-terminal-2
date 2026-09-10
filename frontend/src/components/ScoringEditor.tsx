"use client";

import React, { useState, useEffect } from "react";
import { createPortal } from "react-dom";
import { Settings, X, RefreshCcw, Save } from "lucide-react";
import { fetchScoringConfig, updateScoringConfig, resetScoringConfig, triggerScan } from "../lib/api";

interface ScoringEditorProps {
    onClose: () => void;
}

const EDITOR_KEYS = [
    { key: "COILED_STRUCTURE", label: "Coiled Consolidation", defaultVal: 15 },
    { key: "VWAP_CONFLUENCE", label: "VWAP Pivot Area", defaultVal: 10 },
    { key: "LIQUIDITY_BONUS", label: "Heavy Bid Wall (>$5M)", defaultVal: 10 },
    { key: "RS_BTC_STRONG", label: "Relative Strength (Outperforming BTC)", defaultVal: 10 },
    { key: "OVERBOUGHT_RSI_1H", label: "RSI 1H Overbought Penalty", defaultVal: -15 },
    { key: "VERY_HIGH_CHANGE", label: "Chasing Extended Coins Penalty", defaultVal: -15 },
];

export default function ScoringEditor({ onClose }: ScoringEditorProps) {
    const [weights, setWeights] = useState<Record<string, number>>({});
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [mounted, setMounted] = useState(false);

    useEffect(() => {
        setMounted(true);
        fetchScoringConfig().then((data) => {
            const comps = data.components || {};
            const initial: Record<string, number> = {};
            EDITOR_KEYS.forEach((cfg) => {
                initial[cfg.key] = comps[cfg.key]?.points ?? cfg.defaultVal;
            });
            setWeights(initial);
            setLoading(false);
        }).catch((err) => {
            console.error("Failed to load scoring", err);
            setLoading(false);
        });
    }, []);

    const handleChange = (key: string, val: number) => {
        setWeights(prev => ({ ...prev, [key]: val }));
    };

    const handleSave = async () => {
        setSaving(true);
        const payload: Record<string, any> = {};
        for (const [k, v] of Object.entries(weights)) {
            payload[k] = { points: v };
        }

        try {
            await updateScoringConfig({ components: payload });
            await triggerScan();
            onClose();
        } catch (e) {
            console.error("Save failed", e);
        }
        setSaving(false);
    };

    const handleReset = async () => {
        setSaving(true);
        try {
            await resetScoringConfig();
            await triggerScan();
            onClose();
        } catch (e) {
            console.error("Reset failed", e);
        }
        setSaving(false);
    };

    if (!mounted || loading) {
        if (!mounted) return null;
        return createPortal(
            <div className="overlay-container">
                <div className="editor-modal">Loading configuration...</div>
            </div>,
            document.body
        );
    }

    return createPortal(
        <div className="overlay-container">
            <div className="editor-modal">
                <div className="editor-header">
                    <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                        <Settings size={18} color="#06B6D4" />
                        <h2 style={{ margin: 0, fontSize: "1rem", fontWeight: 700, letterSpacing: "0.03em" }}>
                            EDGE CONFIGURATION
                        </h2>
                    </div>
                    <button className="icon-btn" onClick={onClose}><X size={18} /></button>
                </div>

                <div className="editor-body">
                    <p style={{ margin: "0 0 1rem 0", fontSize: "0.75rem", color: "#8E9BB0", lineHeight: 1.5 }}>
                        Dynamically tweak the scanner's scoring algorithm. Higher weights boost coins containing that feature to the top of the desk. Changes take effect instantly on the next engine cycle.
                    </p>

                    <div className="sliders-container">
                        {EDITOR_KEYS.map((kcfg) => {
                            const val = weights[kcfg.key] || 0;
                            const isPenalty = kcfg.defaultVal < 0;
                            const color = isPenalty ? "#F43F5E" : "#10B981";
                            return (
                                <div key={kcfg.key} className="slider-group">
                                    <div className="slider-header">
                                        <label>{kcfg.label}</label>
                                        <span style={{ color, fontWeight: 700, fontFamily: "JetBrains Mono" }}>
                                            {val > 0 ? `+${val}` : val}
                                        </span>
                                    </div>
                                    <input
                                        type="range"
                                        min="-30"
                                        max="30"
                                        value={val}
                                        onChange={(e) => handleChange(kcfg.key, parseInt(e.target.value))}
                                        style={{ accentColor: color }}
                                    />
                                    <div className="slider-ticks">
                                        <span>-30</span>
                                        <span>0</span>
                                        <span>+30</span>
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                </div>

                <div className="editor-footer">
                    <button className="reset-btn" onClick={handleReset} disabled={saving}>
                        <RefreshCcw size={14} /> RESET DEFAULTS
                    </button>
                    <button className="save-btn" onClick={handleSave} disabled={saving}>
                        <Save size={14} /> {saving ? "APPLYING..." : "SAVE & APPLY"}
                    </button>
                </div>
            </div>

            <style dangerouslySetInnerHTML={{
                __html: `
                .overlay-container {
                    position: fixed;
                    top: 0; left: 0; right: 0; bottom: 0;
                    background: rgba(4, 6, 12, 0.85);
                    backdrop-filter: blur(4px);
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    z-index: 1000;
                }
                .editor-modal {
                    background: #0B0F19;
                    border: 1px solid rgba(255,255,255,0.08);
                    border-radius: 0;
                    width: 480px;
                    max-width: 90vw;
                    box-shadow: 0 20px 40px rgba(0,0,0,0.5);
                    overflow: hidden;
                    display: flex;
                    flex-direction: column;
                }
                .editor-header {
                    padding: 1rem 1.2rem;
                    border-bottom: 1px solid rgba(255,255,255,0.05);
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                }
                .icon-btn {
                    background: none; border: none; color: #64748B; cursor: pointer;
                    display: flex; align-items: center; padding: 0.2rem;
                    transition: color 0.15s;
                }
                .icon-btn:hover { color: #FFF; }
                .editor-body {
                    padding: 1.2rem;
                    max-height: 60vh;
                    overflow-y: auto;
                }
                .sliders-container {
                    display: flex;
                    flex-direction: column;
                    gap: 1.2rem;
                }
                .slider-group {
                    display: flex;
                    flex-direction: column;
                    gap: 0.4rem;
                }
                .slider-header {
                    display: flex;
                    justify-content: space-between;
                    font-size: 0.75rem;
                    color: #E2E8F0;
                    text-transform: uppercase;
                    letter-spacing: 0.03em;
                }
                input[type=range] {
                    width: 100%;
                    cursor: pointer;
                    background: rgba(255,255,255,0.1);
                    height: 4px;
                    border-radius: 0;
                    appearance: none;
                }
                input[type=range]::-webkit-slider-thumb {
                    appearance: none;
                    width: 12px; height: 12px;
                    border-radius: 50%;
                    background: currentColor;
                }
                .slider-ticks {
                    display: flex;
                    justify-content: space-between;
                    font-size: 0.6rem;
                    color: #64748B;
                    font-family: "JetBrains Mono";
                }
                .editor-footer {
                    padding: 1rem 1.2rem;
                    border-top: 1px solid rgba(255,255,255,0.05);
                    background: #080A0F;
                    display: flex;
                    justify-content: space-between;
                }
                .reset-btn {
                    background: none;
                    border: 1px solid rgba(255,255,255,0.1);
                    color: #64748B;
                    padding: 0.5rem 1rem;
                    border-radius: 0;
                    font-size: 0.72rem;
                    font-weight: 700;
                    cursor: pointer;
                    display: flex; align-items: center; gap: 0.4rem;
                }
                .reset-btn:hover { border-color: rgba(255,255,255,0.3); color: #E2E8F0; }
                .save-btn {
                    background: #06B6D4;
                    border: none;
                    color: #04060C;
                    padding: 0.5rem 1.2rem;
                    border-radius: 0;
                    font-size: 0.72rem;
                    font-weight: 800;
                    cursor: pointer;
                    display: flex; align-items: center; gap: 0.4rem;
                }
                .save-btn:hover { background: #08D9FA; }
            `}} />
        </div>,
        document.body
    );
}
