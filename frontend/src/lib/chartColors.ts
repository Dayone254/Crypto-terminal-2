/**
 * Literal colours for CANVAS renderers.
 *
 * `klinecharts` paints into a `<canvas>`, and a canvas 2D context has no
 * access to the CSS custom properties declared in globals.css. Assigning
 * `ctx.fillStyle = "var(--pos)"` is not a legal colour, so the browser silently
 * falls back to black — which is how the colour-token migration turned every
 * candle dark without raising a single error.
 *
 * So the rule is:
 *   · anything painted through the DOM uses `var(--token)`;
 *   · anything handed to a chart library must come from here.
 *
 * These values mirror globals.css by hand and MUST be kept in step with it. If a
 * token changes there and not here, the chart drifts out of the design system
 * silently — so prefer adding a constant here over typing a hex into a chart.
 */

export const CHART_COLORS = {
    // semantic state
    pos: "#10B981",
    posBright: "#34D399",
    neg: "#F43F5E",
    negBright: "#F87171",
    warn: "#F59E0B",
    warnBright: "#FBBF24",
    warnDeep: "#F97316",
    info: "#06B6D4",
    sky: "#38BDF8",
    blue: "#3B82F6",
    blueBright: "#60A5FA",
    purple: "#A855F7",
    purpleBright: "#C084FC",

    // indicator colors
    ema20: "#06B6D4",     // Cyan
    ema50: "#A855F7",     // Purple
    ema200: "#F59E0B",    // Amber
    sma: "#38BDF8",       // Sky blue
    bollUpper: "#EC4899", // Pink
    bollMid: "#8B5CF6",   // Violet
    bollLower: "#EC4899", // Pink
    rsiLine: "#A855F7",   // Purple
    macdLine: "#38BDF8",  // Sky blue
    macdSignal: "#F59E0B",// Amber
    vwapLine: "#3B82F6",  // Blue

    // text ramp
    text1: "#F8FAFC",
    text2: "#E2E8F0",
    text3: "#94A3B8",
    text4: "#748AA0",
    textStrong: "#FFFFFF",
    textInverse: "#000000",

    // surfaces & lines
    surface0: "#06080F",
    surface1: "#0B0F19",
    surface2: "#0E1424",
    surface3: "#080A0F",
    line: "rgba(255, 255, 255, 0.08)",
    lineStrong: "rgba(255, 255, 255, 0.14)",

    // candles
    candleUp: "#10B981",
    candleDown: "#F43F5E",
    candleNoChange: "#748AA0",
} as const;

export type ChartColor = keyof typeof CHART_COLORS;

/**
 * Hex + alpha as one string. A canvas needs a single colour value, so the
 * tinted fills that CSS expresses as `color-mix` or a separate alpha channel
 * have to be composed here.
 */
export const withAlpha = (hex: string, alpha: number): string => {
    const h = hex.replace("#", "");
    const r = parseInt(h.slice(0, 2), 16);
    const g = parseInt(h.slice(2, 4), 16);
    const b = parseInt(h.slice(4, 6), 16);
    return `rgba(${r}, ${g}, ${b}, ${alpha})`;
};

/** The candle series, in one place so the four colour slots cannot half-match. */
export const CANDLE_COLORS = {
    up: CHART_COLORS.candleUp,
    down: CHART_COLORS.candleDown,
    noChange: CHART_COLORS.candleNoChange,
} as const;
