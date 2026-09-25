"use client";

import React from "react";
import { CandidateRow, ScoreInputs } from "@/lib/api";
import { CoverageBadge } from "@/components/CoverageBadge";
import { Activity, BarChart2, Brain, Layers, Waves, Zap } from "lucide-react";

/**
 * The evidence card.
 *
 * This panel previously asserted four specific technical facts that were never
 * computed — "Structure: Strong", "Momentum: Coiled", "Volume: Liquid",
 * "Discounted Range Zone" — as literal strings, and its prose claimed things
 * like "RSI < 45 on 1h" without ever reading an RSI. A card whose whole purpose
 * is to explain a decision cannot invent its own evidence.
 *
 * Every line below is derived from a value that was actually recorded, and says
 * "no data" when there is none.
 */

type Tone = "pos" | "neg" | "neutral" | "absent";

interface EvidenceRow {
    icon: React.ReactNode;
    label: string;
    value: string;
    verdict: string;
    tone: Tone;
    /**
     * The weighted component this reading drives. Each row's `tone` is taken from
     * that component's sign in the persisted breakdown, so this card and the score
     * table beneath it cannot tell different stories — a reading reads as
     * "supporting" exactly when the model actually paid for it.
     */
    component?: string;
}

const TONE_COLORS: Record<Tone, string> = {
    pos: "var(--pos-bright)",
    neg: "var(--neg)",
    neutral: "var(--warn-bright)",
    absent: "var(--text-dim)",
};

const num = (v: unknown): number | null =>
    typeof v === "number" && Number.isFinite(v) ? v : null;

/** Polarity straight from the scorer: positive reading = the model paid for it. */
const toneFromComponent = (norm: number | null): Tone | null => {
    if (norm === null) return null;
    if (norm > 0.05) return "pos";
    if (norm < -0.05) return "neg";
    return "neutral";
};

/** Honest description of what each label means, taken from the labeler's rules. */
const LABEL_MEANING: Record<string, string> = {
    ENTRY_ZONE: "price is inside its limit-ladder entry zone",
    COILED: "price is compressed in the mid-range, before a directional move",
    EARLY: "early structural strength, ahead of the chase phase",
    CHASE: "price has already extended — chasing here is what the scanner rejects",
    WATCH: "monitored, but no entry criteria are met yet",
    SKIP: "excluded — it fails a hard requirement",
};

function rsiRow(rsi: number | null, dir: string): EvidenceRow {
    const icon = <Activity size={12} color="var(--accent-purple-bright)" />;
    const short = dir === "SHORT";
    const base = { icon, label: "Momentum · RSI 1h", component: "momentum" };
    if (rsi === null) {
        return { ...base, value: "—", verdict: "no data", tone: "absent" };
    }
    const v = rsi.toFixed(1);
    // The scorer's momentum term is mirrored between directions: the long side is
    // rewarded for a low RSI and the short side for a high one. Reading "oversold"
    // as supportive on a short — which this panel used to do — directly
    // contradicted the score table right below it, where momentum read negative.
    if (rsi < 30) return { ...base, value: v, verdict: short ? "deeply oversold · headwind" : "deeply oversold", tone: short ? "neg" : "pos" };
    if (rsi < 40) return { ...base, value: v, verdict: short ? "oversold · headwind" : "oversold", tone: short ? "neg" : "pos" };
    if (rsi <= 60) return { ...base, value: v, verdict: "neutral band", tone: "neutral" };
    if (rsi <= 70) return { ...base, value: v, verdict: short ? "elevated · supportive" : "elevated · headwind", tone: short ? "pos" : "neg" };
    return { ...base, value: v, verdict: short ? "overbought · supportive" : "overbought", tone: short ? "pos" : "neg" };
}

function volatilityRow(bbWidth: number | null, dir: string): EvidenceRow {
    const icon = <Waves size={12} color="var(--accent-cyan)" />;
    const short = dir === "SHORT";
    const base = {
        icon,
        label: "Volatility · BB width 1h",
        component: short ? "volatility_expansion" : "volatility_compression",
    };
    if (bbWidth === null) {
        return { ...base, value: "—", verdict: "no data", tone: "absent" };
    }
    const pct = `${(bbWidth * 100).toFixed(1)}%`;
    // No polarity word here, deliberately: the component is
    //   (1 - distance_from_midrange) * band_tightness * 2 - 1
    // so a wide band far from midrange scores *negative*. "Expanded" on its own
    // cannot tell you which way that lands, and guessing wrong is what put a red
    // reading under the word "supportive". The tone is taken from the component.
    if (bbWidth < 0.04) return { ...base, value: pct, verdict: "compressed", tone: "neutral" };
    if (bbWidth < 0.08) return { ...base, value: pct, verdict: "normal", tone: "neutral" };
    return { ...base, value: pct, verdict: "expanded", tone: "neutral" };
}

function volumeRow(volRatio: number | null, notional: number): EvidenceRow {
    const icon = <BarChart2 size={12} color="var(--accent-blue)" />;
    const liquid = `$${(notional / 1_000_000).toFixed(2)}M 24h`;
    // The weighted component reads notional liquidity. The ratio only gates the
    // volume-expansion adjustment, so it is reported alongside without a verdict
    // of its own.
    const base = { icon, label: "Volume · liquidity", component: "liquidity" };
    const value = volRatio === null ? liquid : `${liquid} · ${volRatio.toFixed(2)}× avg`;
    if (notional >= 5_000_000) return { ...base, value, verdict: "deep", tone: "pos" };
    if (notional >= 1_000_000) return { ...base, value, verdict: "above floor", tone: "neutral" };
    return { ...base, value, verdict: "below floor", tone: "neg" };
}

function relativeStrengthRow(rs7: number | null, dir: string): EvidenceRow {
    const icon = <Zap size={12} color="var(--accent-amber)" />;
    const short = dir === "SHORT";
    const base = {
        icon,
        label: "Relative strength · 7d vs BTC",
        component: short ? "relative_weakness" : "relative_strength",
    };
    if (rs7 === null) {
        return { ...base, value: "—", verdict: "no data", tone: "absent" };
    }
    const v = `${rs7 >= 0 ? "+" : "−"}${Math.abs(rs7).toFixed(1)}%`;
    if (rs7 > 2) return { ...base, value: v, verdict: short ? "outperforming · headwind" : "outperforming", tone: short ? "neg" : "pos" };
    if (rs7 < -2) return { ...base, value: v, verdict: short ? "underperforming · supportive" : "underperforming", tone: short ? "pos" : "neg" };
    return { ...base, value: v, verdict: "in line", tone: "neutral" };
}

function rangeRow(pir: number): EvidenceRow {
    const icon = <Layers size={12} color="var(--accent-cyan)" />;
    const v = pir.toFixed(2);
    // Position in range carries no weighted component — the labeler reads it, the
    // scorer does not — so it is described, never scored as supporting or opposing.
    if (pir < 0.35) return { icon, label: "Range position · PIR", value: v, verdict: "lower third of today", tone: "neutral" };
    if (pir <= 0.65) return { icon, label: "Range position · PIR", value: v, verdict: "mid-range", tone: "neutral" };
    return { icon, label: "Range position · PIR", value: v, verdict: "upper third of today", tone: "neutral" };
}

function bookRow(buy: number | null, sell: number | null, dir: string): EvidenceRow {
    const icon = <BarChart2 size={12} color="var(--accent-emerald)" />;
    const short = dir === "SHORT";
    const fmt = (n: number) => `$${n >= 1_000_000 ? `${(n / 1_000_000).toFixed(2)}M` : `${Math.round(n / 1000)}k`}`;
    const base = {
        icon,
        label: "Order book · within 2%",
        component: short ? "l2_resistance" : "l2_support",
    };
    if (buy === null && sell === null) {
        return { ...base, value: "—", verdict: "no data", tone: "absent" };
    }
    const value = [
        buy !== null ? `${fmt(buy)} bids` : "bids —",
        sell !== null ? `${fmt(sell)} asks` : "asks —",
    ].join(" / ");
    // The model weighs one side only — asks overhead for a short, bids beneath for a
    // long — at a $250k full-credit scale. So the verdict describes *that* side,
    // rather than which side of the book happens to be larger. Calling a bid-heavy
    // book "support" for a short, as this panel used to, is exactly backwards.
    const relevant = short ? sell : buy;
    const side = short ? "asks" : "bids";
    if (relevant === null) {
        return { ...base, value, verdict: `${side} not measured`, tone: "absent" };
    }
    const verdict =
        relevant >= 250_000 ? `${side} ≥$250k · full credit`
            : relevant >= 100_000 ? `${side} meaningful`
                : `${side} thin`;
    return { ...base, value, verdict, tone: relevant >= 100_000 ? "pos" : "neutral" };
}

export function TradeReasoningCard({
    candidate,
    inputs,
    components,
    coverage,
    direction,
    rank,
}: {
    candidate: CandidateRow;
    inputs?: ScoreInputs | null;
    /** Persisted normalised components — the source of each row's polarity. */
    components?: Record<string, number> | null;
    coverage?: number | null;
    direction?: string;
    rank?: { position: number; total: number } | null;
}) {
    const rsi = num(inputs?.rsi_1h);
    const bbWidth = num(inputs?.bb_width_1h);
    const volRatio = num(inputs?.volume_ratio_1h);
    const rs7 = num(inputs?.rs_vs_btc_7d);
    const l2Buy = num(inputs?.l2_buy_vol_2pct);
    const l2Sell = num(inputs?.l2_sell_vol_2pct);

    const dir = direction || candidate.trade_direction || "LONG";
    /** Without recorded inputs there is nothing to show — and nothing to claim. */
    const hasInputs = !!inputs;

    const rows: EvidenceRow[] = [
        rsiRow(rsi, dir),
        volatilityRow(bbWidth, dir),
        volumeRow(volRatio, candidate.quote_vol_24h),
        relativeStrengthRow(rs7, dir),
        rangeRow(candidate.pos_in_range),
        bookRow(l2Buy, l2Sell, dir),
    ].map((row) => {
        // Take the polarity from the model's own arithmetic wherever a weighted
        // component covers the reading; the authored tone is only a fallback for
        // rows the scorer does not weigh. This is what stops the card from
        // disagreeing with the score table rendered directly beneath it.
        if (!row.component) return row;
        const tone = toneFromComponent(num(components?.[row.component]));
        return tone ? { ...row, tone } : row;
    });

    const meaning = LABEL_MEANING[candidate.label] ?? "monitored";
    const scale = `The ${dir} score of ${candidate.composite_score.toFixed(0)} is drawn from ${dir === "SHORT" ? "trend weakness, relative weakness, volatility, momentum, liquidity and ask-side depth" : "trend strength, relative strength, volatility, momentum, liquidity and bid-side depth"}.`;

    const supporting = rows
        .filter((r) => r.tone === "pos")
        .slice(0, 2)
        .map((r) => `${r.label.split(" · ")[0]} ${r.verdict} (${r.value})`);
    // Only meaningful when inputs were recorded. Without them every row would read
    // "no data" and this would claim the score was shrunk for missing evidence —
    // which it was not: the evidence simply was not recorded, so we say nothing.
    const missing = hasInputs ? rows.filter((r) => r.tone === "absent").length : 0;

    return (
        <div className="panel" style={{ padding: "var(--sp-5)", display: "flex", flexDirection: "column", gap: "var(--sp-4)" }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.5rem", flexWrap: "wrap" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                    <Brain size={18} color="var(--accent-emerald)" />
                    <span style={{ fontWeight: 800, fontSize: "0.9rem", color: "var(--text-strong)" }}>WHAT THE SCANNER SAW</span>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                    {rank && (
                        <span className="mono" style={{ fontSize: "0.6rem", color: "var(--text-muted)" }}>
                            #{rank.position} of {rank.total} today
                        </span>
                    )}
                    <CoverageBadge coverage={coverage} band={candidate.coverage_band} edge={candidate.edge} />
                </div>
            </div>

            {/* Honest one-line summary, assembled only from facts we hold. */}
            <div style={{ background: "rgba(16, 185, 129, 0.08)", padding: "0.85rem", display: "flex", flexDirection: "column", gap: "0.45rem" }}>
                <span style={{ color: "var(--pos-bright)", fontWeight: 800, fontSize: "0.75rem" }}>
                    Labelled {candidate.label} — {meaning}
                </span>
                <p style={{ color: "var(--text-2)", fontSize: "0.75rem", lineHeight: 1.6, margin: 0 }}>
                    {scale}
                    {supporting.length > 0 && <> Supporting evidence: {supporting.join("; ")}.</>}
                    {supporting.length === 0 && <> No component reads strongly enough to cite.</>}
                    {missing > 0 && (
                        <> {missing} of {rows.length} inputs were not available this scan, so the score is shrunk toward neutral by exactly that gap.</>
                    )}
                </p>
            </div>

            {/* Evidence grid — every value below was recorded, or says so. */}
            {hasInputs ? (
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.75rem" }}>
                    {rows.map((r) => (
                        <div key={r.label} style={{ background: "rgba(0,0,0,0.4)", padding: "0.6rem 0.8rem", display: "flex", flexDirection: "column", gap: "0.15rem" }}>
                            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", color: "var(--text-muted)", fontSize: "0.65rem", gap: "0.4rem" }}>
                                <span style={{ display: "flex", alignItems: "center", gap: "0.3rem" }}>{r.icon}{r.label}</span>
                                <span style={{ color: TONE_COLORS[r.tone], fontWeight: 800, textAlign: "right" }}>{r.verdict}</span>
                            </div>
                            <div className="mono" style={{ color: r.tone === "absent" ? "var(--text-dim)" : "var(--text-strong)", fontWeight: 700, fontSize: "0.75rem" }}>
                                {r.value}
                            </div>
                        </div>
                    ))}
                </div>
            ) : (
                <div className="empty-state">
                    <span>
                        No inputs were recorded with this score, so none of these readings can be shown.
                        Scores persisted before the flight recorder went in carry no evidence — run a scan to populate it.
                    </span>
                </div>
            )}

            {candidate.tags && candidate.tags.length > 0 && (
                <div>
                    <span style={{ fontSize: "0.65rem", color: "var(--text-dim)", fontWeight: 700, textTransform: "uppercase", display: "block", marginBottom: "0.4rem" }}>
                        Confluence tags
                    </span>
                    <div style={{ display: "flex", flexWrap: "wrap", gap: "0.4rem" }}>
                        {candidate.tags.map((tag) => (
                            <span key={tag} className="mono" style={{ padding: "0.2rem 0.5rem", background: "rgba(6,182,212,0.15)", color: "var(--accent-cyan)", fontWeight: 800, fontSize: "0.7rem" }}>
                                #{tag}
                            </span>
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
}
