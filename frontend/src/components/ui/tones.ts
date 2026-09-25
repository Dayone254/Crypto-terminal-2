/**
 * One vocabulary of colour roles for the whole app.
 *
 * Named for meaning rather than hue, so a component asks for "negative" and the
 * token layer decides that means rose. That indirection is what stops the drift
 * that put 39 distinct hex values and five accidental near-blacks into the
 * codebase: there is now exactly one place where a role maps to a colour.
 */

export type Tone =
    | "pos"      // up, long, supportive, healthy
    | "neg"      // down, short, headwind, risk
    | "warn"     // caution, missing evidence, stale
    | "warnDeep" // one step more severe than warn (4-step severity ramps)
    | "info"     // neutral emphasis, interaction
    | "accent"   // secondary emphasis (purple)
    | "neutral"  // body text emphasis
    | "dim"      // de-emphasised
    | "absent";  // explicitly no data

/** Foreground colour for a role. */
export const TONE_VAR: Record<Tone, string> = {
    pos: "var(--pos)",
    neg: "var(--neg)",
    warn: "var(--warn)",
    warnDeep: "var(--warn-deep)",
    info: "var(--info)",
    accent: "var(--accent-purple)",
    neutral: "var(--text-2)",
    dim: "var(--text-4)",
    absent: "var(--text-4)",
};

/** Tint fill for a role — the translucent background behind a badge or chip. */
export const TONE_SOFT: Record<Tone, string> = {
    pos: "var(--pos-soft)",
    neg: "var(--neg-soft)",
    warn: "var(--warn-soft)",
    warnDeep: "var(--warn-deep-soft)",
    info: "var(--info-soft)",
    accent: "var(--purple-soft)",
    neutral: "var(--hover)",
    dim: "var(--hover)",
    absent: "var(--hover)",
};

/** Border colour for a role. */
export const TONE_LINE: Record<Tone, string> = {
    pos: "var(--pos-line)",
    neg: "var(--neg-line)",
    warn: "var(--warn-line)",
    warnDeep: "var(--warn-deep-line)",
    info: "var(--info-line)",
    accent: "rgba(168, 85, 247, 0.35)",
    neutral: "var(--line)",
    dim: "var(--line)",
    absent: "var(--line)",
};

/** Brighter foreground for emphasis — large figures, active states. */
export const TONE_VAR_BRIGHT: Record<Tone, string> = {
    ...TONE_VAR,
    pos: "var(--pos-bright)",
    neg: "var(--neg-bright)",
    warn: "var(--warn-bright)",
};

/** Anything money-shaped: sign decides the role. */
export const signTone = (v: number | null | undefined): Tone =>
    v === null || v === undefined || v === 0 ? "dim" : v > 0 ? "pos" : "neg";

/** Format a signed percentage with the app's minus sign (U+2212, not a hyphen). */
export const signedPct = (v: number, digits = 2): string =>
    `${v >= 0 ? "+" : "\u2212"}${Math.abs(v).toFixed(digits)}%`;
