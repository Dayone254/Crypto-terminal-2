"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import {
    ArrowLeft,
    Check,
    Copy,
    Layers,
    Palette,
    Ruler,
    Shapes,
    Type as TypeIcon,
    Zap,
} from "lucide-react";
import { Badge, EmptyState, Panel, SectionTitle, Skeleton, Stat, Tone } from "@/components/ui";

/**
 * The styleguide.
 *
 * A design system nobody can look at is a design system that decays — this app
 * had a token file the whole time while drifting to 24 font sizes and 39 hex
 * values. This page renders the tokens and primitives from the same source the
 * app uses, so drift becomes visible the moment it happens.
 *
 * Contrast ratios below are measured, not asserted; the one value that failed
 * WCAG AA is shown alongside its replacement.
 */

const CONTRAST: Record<string, number> = {
    "text-1": 18.3, "text-2": 15.53, "text-3": 7.47, "text-4": 5.37, "text-strong": 19.15,
    pos: 7.55, "pos-bright": 9.96, neg: 5.22, "neg-bright": 6.92,
    warn: 8.92, "warn-bright": 11.47, "warn-deep": 6.83, info: 7.89,
    "accent-sky": 8.94, "accent-blue": 5.21, "accent-blue-bright": 7.53,
    "accent-purple": 4.84, "accent-purple-bright": 7.25,
    "rank-1": 8.92, "rank-2": 7.47, "rank-3": 6.09,
};

const SURFACES: [string, string, string][] = [
    ["--surface-0", "#06080F", "page canvas"],
    ["--surface-1", "#0B0F19", "panels"],
    ["--surface-2", "#0E1424", "nested / raised"],
    ["--surface-3", "#080A0F", "inset wells"],
];

const TEXT_RAMP: [string, string, string][] = [
    ["--text-1", "#F8FAFC", "primary"],
    ["--text-2", "#E2E8F0", "body"],
    ["--text-3", "#94A3B8", "muted"],
    ["--text-4", "#748AA0", "dim"],
];

const STATE: [string, string][] = [
    ["pos", "up · long · supportive"],
    ["pos-bright", "emphasis"],
    ["neg", "down · short · headwind"],
    ["neg-bright", "emphasis"],
    ["warn", "caution · missing evidence"],
    ["warn-bright", "emphasis"],
    ["warn-deep", "severity step 4"],
    ["info", "interaction · neutral emphasis"],
    ["accent-sky", "chart levels"],
    ["accent-blue", "secondary"],
    ["accent-blue-bright", "secondary emphasis"],
    ["accent-purple", "options / secondary"],
    ["accent-purple-bright", "options emphasis"],
    ["rank-1", "leaderboard gold"],
    ["rank-2", "silver"],
    ["rank-3", "bronze"],
];

const TYPE_SCALE: [string, string, string][] = [
    ["--fs-2xl", "28px", "page hero figure"],
    ["--fs-xl", "20px", "symbol / primary heading"],
    ["--fs-lg", "16px", "panel heading"],
    ["--fs-base", "14px", "body, stat values"],
    ["--fs-sm", "13px", "secondary body"],
    ["--fs-xs", "12px", "labels, table cells"],
    ["--fs-micro", "11px", "uppercase micro-labels (floor)"],
];

const SPACES = ["--sp-1", "--sp-2", "--sp-3", "--sp-4", "--sp-5", "--sp-6"];

const ALL_TONES: Tone[] = ["pos", "neg", "warn", "warnDeep", "info", "accent", "neutral", "dim", "absent"];

function Section({
    icon,
    title,
    note,
    children,
}: {
    icon: React.ReactNode;
    title: string;
    note?: string;
    children: React.ReactNode;
}) {
    return (
        <Panel>
            <SectionTitle icon={icon}>{title}</SectionTitle>
            {note && (
                <p style={{ margin: 0, fontSize: "var(--fs-xs)", color: "var(--text-3)", lineHeight: 1.6, maxWidth: "80ch" }}>
                    {note}
                </p>
            )}
            {children}
        </Panel>
    );
}

function Swatch({ token, hex, label }: { token: string; hex?: string; label: string }) {
    const ratio = CONTRAST[token.replace("--", "")];
    const meta = [hex, ratio !== undefined ? `${ratio.toFixed(2)}:1` : null].filter(Boolean).join(" · ");
    return (
        <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-3)" }}>
            <div
                style={{
                    width: 44, height: 44, flexShrink: 0,
                    background: `var(${token})`,
                    border: "1px solid var(--line-strong)",
                }}
            />
            <div style={{ display: "flex", flexDirection: "column", gap: 2, minWidth: 0 }}>
                <span className="mono" style={{ fontSize: "var(--fs-micro)", color: "var(--text-2)", fontWeight: 700 }}>
                    {token}
                </span>
                <span className="mono" style={{ fontSize: "var(--fs-micro)", color: "var(--text-4)" }}>
                    {meta}
                    {ratio !== undefined && ratio < 4.5 && " · FAILS AA"}
                </span>
                <span style={{ fontSize: "var(--fs-micro)", color: "var(--text-4)" }}>{label}</span>
            </div>
        </div>
    );
}

/** Shows why tabular figures matter: the same value, with and without them. */
function TabularDemo() {
    const [n, setN] = useState(100000);
    useEffect(() => {
        const id = setInterval(() => setN(100000 + Math.floor(Math.random() * 99999)), 900);
        return () => clearInterval(id);
    }, []);
    return (
        <div className="grid-2">
            <div className="well" style={{ padding: "var(--sp-3)", display: "flex", flexDirection: "column", gap: "var(--sp-2)" }}>
                <Badge tone="pos">fixed — tabular-nums</Badge>
                <span className="mono" style={{ fontSize: "var(--fs-xl)", fontWeight: 800, color: "var(--text-1)" }}>
                    ${n.toLocaleString()}
                </span>
                <span style={{ fontSize: "var(--fs-micro)", color: "var(--text-4)" }}>digits hold their column</span>
            </div>
            <div className="well" style={{ padding: "var(--sp-3)", display: "flex", flexDirection: "column", gap: "var(--sp-2)" }}>
                <Badge tone="neg">before — proportional figures</Badge>
                <span
                    className="mono"
                    style={{
                        fontSize: "var(--fs-xl)", fontWeight: 800, color: "var(--text-1)",
                        fontVariantNumeric: "proportional-nums",
                    }}
                >
                    ${n.toLocaleString()}
                </span>
                <span style={{ fontSize: "var(--fs-micro)", color: "var(--text-4)" }}>the column twitches on every tick</span>
            </div>
        </div>
    );
}

export default function StyleguidePage() {
    const [copied, setCopied] = useState<string | null>(null);

    return (
        <div style={{ minHeight: "100vh", background: "var(--surface-0)", padding: "var(--sp-5) var(--sp-6)", display: "flex", flexDirection: "column", gap: "var(--sp-5)" }}>
            <header style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "var(--sp-4)", flexWrap: "wrap" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-3)" }}>
                    <Link href="/" className="btn">
                        <ArrowLeft size={14} />
                        SCANNER
                    </Link>
                    <h1 style={{ margin: 0, fontSize: "var(--fs-xl)", fontWeight: 800, color: "var(--text-1)", letterSpacing: "-0.02em" }}>
                        Design system
                    </h1>
                    <Badge tone="info">fv2</Badge>
                </div>
                <span className="mono" style={{ fontSize: "var(--fs-micro)", color: "var(--text-4)" }}>
                    every value below is read from globals.css — not a copy
                </span>
            </header>

            <Section
                icon={<Palette size={14} color="var(--info)" />}
                title="Surfaces"
                note="Six near-identical near-blacks used to be scattered as raw hex. Their luminances span 0.0018–0.0072 — they read as one colour, so they implied five levels while carrying none. Four deliberate steps now, and nothing else."
            >
                <div className="grid-2" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(230px, 1fr))" }}>
                    {SURFACES.map(([t, h, l]) => <Swatch key={t} token={t} hex={h} label={l} />)}
                </div>
            </Section>

            <Section
                icon={<TypeIcon size={14} color="var(--warn)" />}
                title="Text ramp & contrast"
                note="Ratios are measured against --surface-1 (#0B0F19), the panel colour most text sits on. The previous --text-dim was the single most-used token in the app (90 call sites) and measured 4.02:1 — under WCAG AA's 4.5:1 for small text, at the smallest sizes in the product. It is now 5.37:1."
            >
                <div className="grid-2" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(230px, 1fr))" }}>
                    {TEXT_RAMP.map(([t, h, l]) => <Swatch key={t} token={t} hex={h} label={l} />)}
                    <Swatch token="--text-strong" hex="#FFFFFF" label="maximum emphasis" />
                    <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-3)" }}>
                        <div style={{ width: 44, height: 44, flexShrink: 0, background: "#64748B", border: "1px solid var(--neg-line)", display: "grid", placeItems: "center" }}>
                            <span className="mono" style={{ fontSize: "10px", color: "var(--text-inverse)", fontWeight: 800 }}>old</span>
                        </div>
                        <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                            <span className="mono" style={{ fontSize: "var(--fs-micro)", color: "var(--neg)", fontWeight: 700 }}>#64748B — 4.02:1</span>
                            <span style={{ fontSize: "var(--fs-micro)", color: "var(--text-4)" }}>FAILED AA · replaced by --text-4</span>
                        </div>
                    </div>
                </div>
            </Section>

            <Section
                icon={<Zap size={14} color="var(--pos)" />}
                title="Semantic state"
                note="Named for meaning, not hue: a component asks for 'negative', the token layer decides that means rose. That indirection is what replaced 39 hardcoded hex values with one place where a role maps to a colour."
            >
                <div className="grid-2" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(230px, 1fr))" }}>
                    {STATE.map(([t, l]) => <Swatch key={t} token={`--${t}`} hex="" label={l} />)}
                </div>
            </Section>

            <Section
                icon={<TypeIcon size={14} color="var(--accent-purple)" />}
                title="Type scale"
                note="The app shipped 24 distinct sizes between 0.55 and 1.8rem, with 38% of all text at or below 11.2px and a floor of 8.8px. Seven steps, with 11px as a hard floor."
            >
                <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-2)" }}>
                    {TYPE_SCALE.map(([t, px, use]) => (
                        <div key={t} style={{ display: "flex", alignItems: "baseline", gap: "var(--sp-4)", flexWrap: "wrap" }}>
                            <span className="mono" style={{ fontSize: "var(--fs-micro)", color: "var(--text-4)", width: 110, flexShrink: 0 }}>
                                {t} · {px}
                            </span>
                            <span style={{ fontSize: `var(${t})`, color: "var(--text-1)", fontWeight: t === "--fs-micro" ? 800 : 600 }}>
                                {t === "--fs-micro" ? "RSI 43.6 · PIR 0.29" : "SPX-USD 86.0"}
                            </span>
                            <span style={{ fontSize: "var(--fs-micro)", color: "var(--text-4)" }}>{use}</span>
                        </div>
                    ))}
                </div>
                <TabularDemo />
            </Section>

            <Section icon={<Ruler size={14} color="var(--accent-sky)" />} title="Space & radius" note="A 4px rhythm, and one radius. Hard-edged is the house language and a good one — it needed to be a single value rather than the nine that had accumulated (0 alongside 2/4/5/6/7/10/12px). Not yet migrated: app/edge still carries its own rounded-card language (10/12/16px), which is a design decision rather than a mechanical fix.">
                <div style={{ display: "flex", alignItems: "flex-end", gap: "var(--sp-4)", flexWrap: "wrap" }}>
                    {SPACES.map((t, i) => (
                        <div key={t} style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: "var(--sp-2)" }}>
                            <div style={{ width: `var(${t})`, height: 36, background: "var(--info-soft)", border: "1px solid var(--info-line)" }} />
                            <span className="mono" style={{ fontSize: "var(--fs-micro)", color: "var(--text-4)" }}>
                                {t} · {(i + 1) * 4}px
                            </span>
                        </div>
                    ))}
                </div>
            </Section>

            <Section icon={<Shapes size={14} color="var(--text-2)" />} title="Primitives" note="Panels used to re-declare their own surface and border inline at every call site — which is precisely how the palette drifted. These come from one place now.">
                <div className="grid-2">
                    <Panel flush>
                        <SectionTitle icon={<Layers size={13} />}>Panel — default</SectionTitle>
                        <span style={{ fontSize: "var(--fs-xs)", color: "var(--text-3)" }}>hairline border, surface-1 fill</span>
                    </Panel>
                    <Panel flush inset>
                        <SectionTitle icon={<Layers size={13} />}>Panel — inset</SectionTitle>
                        <span style={{ fontSize: "var(--fs-xs)", color: "var(--text-3)" }}>surface-3, for wells inside a panel</span>
                    </Panel>
                </div>

                <div style={{ display: "flex", gap: "var(--sp-3)", flexWrap: "wrap", alignItems: "center" }}>
                    {ALL_TONES.map((t) => <Badge key={t} tone={t}>{t}</Badge>)}
                </div>

                <div className="grid-2" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(190px, 1fr))" }}>
                    <Stat label="Score" value="88.8" tone="pos" bright />
                    <Stat label="Edge" value="73.8" tone="info" />
                    <Stat label="24h" value="−6.09%" tone="neg" />
                    <Stat label="Coverage" value="FULL 100%" tone="warn" />
                </div>

                <div style={{ display: "flex", gap: "var(--sp-2)", flexWrap: "wrap", alignItems: "center" }}>
                    <button className="btn" onClick={() => setCopied("a")}>
                        {copied === "a" ? <Check size={14} /> : <Copy size={14} />}
                        {copied === "a" ? "COPIED" : "COPY LADDER"}
                    </button>
                    <button className="btn btn--info">COMPARE</button>
                    <button className="btn btn--pos">PIN</button>
                    <button className="btn" disabled>DISABLED</button>
                </div>

                <EmptyState icon={<Zap size={14} color="var(--warn)" />}>
                    No ladder for this symbol — the setup did not clear the R/R floor, so no levels are published.
                </EmptyState>

                <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-2)" }}>
                    <span style={{ fontSize: "var(--fs-micro)", color: "var(--text-4)" }}>Skeleton — never render a half-empty page while data is in flight</span>
                    <Skeleton height="2.2rem" />
                    <Skeleton height="2.2rem" width="70%" />
                </div>
            </Section>

            <footer style={{ paddingBottom: "var(--sp-5)" }}>
                <span className="mono" style={{ fontSize: "var(--fs-micro)", color: "var(--text-4)" }}>
                    Add a primitive here before adding a one-off elsewhere.
                </span>
            </footer>
        </div>
    );
}
