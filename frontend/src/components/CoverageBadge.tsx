"use client";

import React from "react";
import { Badge, Tone } from "@/components/ui";

/**
 * Coverage is the share of the scoring model's weight that real observations
 * backed. A score cannot be read honestly without it: a 78 resting on three of
 * six components is not the same setup as a 78 resting on all six.
 *
 * The band→role mapping lives here and nowhere else. It previously existed twice,
 * with its own hardcoded hex map, which is how the same green ended up written
 * three different ways across the app.
 */
const BAND_TONE: Record<string, Tone> = {
    FULL: "pos",
    PARTIAL: "warn",
    THIN: "warnDeep",
    BLIND: "neg",
};

/** A score should read as quieter the less evidence stands behind it. */
export function coverageOpacity(coverage?: number | null): number {
    if (coverage === null || coverage === undefined) return 1;
    if (coverage >= 0.85) return 1;
    if (coverage >= 0.6) return 0.92;
    if (coverage > 0) return 0.72;
    return 0.5;
}

export function coverageColor(band?: string | null): string {
    void band;
    return "var(--text-4)";
}

export function coverageTitle(
    coverage?: number | null,
    edge?: number | null,
    band?: string | null,
): string {
    if (coverage === null || coverage === undefined) {
        return "Evidence coverage unknown — scored before the belief state was recorded";
    }
    const bits = [`Evidence backs ${Math.round(coverage * 100)}% of the model's weight`];
    if (band) bits.push(band);
    if (edge !== null && edge !== undefined) bits.push(`edge ${edge.toFixed(1)}/100`);
    return bits.join(" · ");
}

export function CoverageBadge({
    coverage,
    band,
    edge,
    size = "sm",
}: {
    coverage?: number | null;
    band?: string | null;
    edge?: number | null;
    size?: "sm" | "md";
}) {
    const fontSize = size === "md" ? "var(--fs-xs)" : undefined;

    if (coverage === null || coverage === undefined) {
        return (
            <Badge tone="absent" title={coverageTitle(coverage, edge, band)} style={{ fontSize }}>
                NO DATA
            </Badge>
        );
    }

    const pct = `${Math.round(coverage * 100)}%`;
    return (
        <Badge
            tone={BAND_TONE[band ?? ""] ?? "dim"}
            title={coverageTitle(coverage, edge, band)}
            style={{ fontSize }}
        >
            {band ? `${band} ${pct}` : pct}
        </Badge>
    );
}
