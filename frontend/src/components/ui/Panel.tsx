"use client";

import React from "react";
import { Tone, TONE_LINE, TONE_SOFT, TONE_VAR, TONE_VAR_BRIGHT } from "./tones";

/**
 * The fundamental container.
 *
 * Every panel in the app used to re-declare its own surface inline —
 * `background: "var(--surface-1)", border: "none", borderRadius: 0, padding: "1rem"` —
 * which is exactly how the surface palette drifted to six near-identical
 * near-blacks and nine border radii. Panels now come from here.
 */
export function Panel({
    children,
    /** Drop the hairline: for a panel nested inside another panel. */
    flush = false,
    /** Inset surface — chart canvas, code block, nested readout. */
    inset = false,
    title,
    actions,
    padded = true,
    style,
    className = "",
    ...rest
}: {
    children: React.ReactNode;
    flush?: boolean;
    inset?: boolean;
    title?: React.ReactNode;
    actions?: React.ReactNode;
    padded?: boolean;
    style?: React.CSSProperties;
    className?: string;
} & React.HTMLAttributes<HTMLElement>) {
    const cls = ["panel", flush ? "panel--flush" : "", inset ? "panel--inset" : "", className]
        .filter(Boolean)
        .join(" ");

    return (
        <section
            className={cls}
            style={{
                padding: padded ? "var(--sp-4)" : 0,
                display: "flex",
                flexDirection: "column",
                gap: "var(--sp-3)",
                ...style,
            }}
            {...rest}
        >
            {(title || actions) && (
                <header
                    style={{
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "space-between",
                        gap: "var(--sp-3)",
                        flexWrap: "wrap",
                    }}
                >
                    {title}
                    {actions && <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-2)" }}>{actions}</div>}
                </header>
            )}
            {children}
        </section>
    );
}

/**
 * The uppercase micro-label above every group of figures.
 *
 * Sits at the type floor (11px) rather than the 8.8px the app had drifted to,
 * and pairs with `--text-2` so it stays legible instead of receding into the
 * background it labels.
 */
export function SectionTitle({
    icon,
    children,
    tone,
    as: As = "span",
}: {
    icon?: React.ReactNode;
    children: React.ReactNode;
    tone?: Tone;
    as?: "span" | "h2" | "h3";
}) {
    return (
        <As className="sec-title" style={tone ? { color: TONE_VAR[tone] } : undefined}>
            {icon}
            {children}
        </As>
    );
}

/**
 * A label/value readout — the header's "SPOT: $0.48910" shape, repeated with
 * slightly different sizes and colours at a dozen call sites before this existed.
 */
export function Stat({
    label,
    value,
    tone = "neutral",
    bright = false,
    mono = true,
    size = "var(--fs-base)",
    hint,
}: {
    label: string;
    value: React.ReactNode;
    tone?: Tone;
    bright?: boolean;
    mono?: boolean;
    size?: string;
    hint?: string;
}) {
    return (
        <div className="readout" title={hint}>
            <span
                style={{
                    fontSize: "var(--fs-micro)",
                    fontWeight: 800,
                    letterSpacing: "0.06em",
                    textTransform: "uppercase",
                    color: "var(--text-4)",
                }}
            >
                {label}
            </span>
            <span
                className={mono ? "mono" : undefined}
                style={{
                    fontSize: size,
                    fontWeight: 800,
                    color: bright ? TONE_VAR_BRIGHT[tone] : TONE_VAR[tone],
                }}
            >
                {value}
            </span>
        </div>
    );
}

/**
 * A small tonal chip. Replaces the per-component colour maps that had grown up
 * around coverage bands, directions and statuses.
 */
export function Badge({
    children,
    tone = "neutral",
    mono = true,
    title,
    style,
}: {
    children: React.ReactNode;
    tone?: Tone;
    mono?: boolean;
    title?: string;
    style?: React.CSSProperties;
}) {
    return (
        <span
            className={mono ? "mono" : undefined}
            title={title}
            style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "var(--sp-1)",
                padding: "2px 6px",
                background: TONE_SOFT[tone],
                border: `1px solid ${TONE_LINE[tone]}`,
                color: TONE_VAR[tone],
                fontSize: "var(--fs-micro)",
                fontWeight: 800,
                letterSpacing: "0.04em",
                whiteSpace: "nowrap",
                ...style,
            }}
        >
            {children}
        </span>
    );
}

/**
 * The honest empty state. Used wherever the page previously invented data rather
 * than admitting a gap.
 */
export function EmptyState({
    icon,
    children,
    style,
}: {
    icon?: React.ReactNode;
    children: React.ReactNode;
    style?: React.CSSProperties;
}) {
    return (
        <div className="empty-state" style={style}>
            {icon}
            <span>{children}</span>
        </div>
    );
}

/** Loading placeholder. Do not render a half-empty page while data is in flight. */
export function Skeleton({
    height = "1rem",
    width = "100%",
    style,
}: {
    height?: string | number;
    width?: string | number;
    style?: React.CSSProperties;
}) {
    return <div className="skeleton" style={{ height, width, ...style }} />;
}
