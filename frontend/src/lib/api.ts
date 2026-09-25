/**
 * Typed API client for the TPT backend.
 *
 * All backend access goes through this module so the base URL, auth header and
 * WebSocket scheme are defined in exactly one place.
 */

export const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

/** Derive the WS base from API_BASE so TLS deployments get wss:// automatically. */
export function wsBase(): string {
    return API_BASE.replace(/^http/, "ws");
}

const API_TOKEN = process.env.NEXT_PUBLIC_API_TOKEN || "";

/** Headers for every API call (adds the optional shared-secret token). */
export function apiHeaders(extra: Record<string, string> = {}): Record<string, string> {
    return API_TOKEN ? { "X-API-Token": API_TOKEN, ...extra } : { ...extra };
}

/** fetch() against the backend with base URL, auth and cache policy applied. */
export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
    return fetch(`${API_BASE}${path}`, {
        cache: "no-store",
        ...init,
        headers: apiHeaders((init.headers as Record<string, string>) || {}),
    });
}

export interface CandidateRow {
    product_id: string;
    last_price: number;
    day_change_pct: number;
    composite_score: number;
    /**
     * Belief state. `edge` is how good the evidence was, `coverage` is how much
     * of the model that evidence actually spans, and `coverage_band` is the
     * coarse label for it. A score without these cannot be read honestly: a 78
     * ranked on three of six components is not the same setup as a 78 ranked on
     * all six, and until these were carried through nothing could tell them apart.
     */
    edge?: number | null;
    coverage?: number | null;
    coverage_band?: string | null;
    trade_direction: string;
    label: string;
    pos_in_range: number;
    quote_vol_24h: number;
    ladder: LadderLevels | null;
    tags: string[];
    pinned: boolean;
}

export interface LadderLevels {
    trade_direction?: string;
    tranche_a_price: number;
    tranche_b_price: number;
    stop_price: number;
    target_1_price: number;
    target_2_price: number | null;
    tranche_a_size_pct?: number;
    tranche_b_size_pct?: number;
    rr_a_t1?: number;
    rr_a_t2?: number;
    basis?: Record<string, number | null>;
}

export type CandidateLadder = LadderLevels;

/** Dealer gamma exposure board (only populated for underlyings with an options chain, e.g. BTC/ETH). */
export interface GammaWall {
    strike: number;
    gex_impact: number;
    type: "RESISTANCE" | "SUPPORT";
}

export interface OptionsFlow {
    total_net_gex: number;
    net_dealer_delta?: number;
    net_dealer_theta?: number;
    net_dealer_vega?: number;
    iv_skew?: number;
    gamma_walls: GammaWall[];
    gamma_flip: number;
}

export interface FeatureMetrics {
    last_price?: number;
    vwap_24h?: number;
    fib_236?: number;
    fib_382?: number;
    fib_500?: number;
    fib_618?: number;
    fib_786?: number;
    swing_shelf_7d?: number;
    swing_high_7d?: number;
}

/**
 * The scorer's own arithmetic, as persisted alongside the score.
 *
 * `components` holds the *normalised* readings (all in [-1, 1]) that went into
 * the weighted sum; the `*_interactions` fields are point adjustments applied on
 * top of it. Carrying this through to the UI is what lets the page say *why* a
 * score is what it is, instead of merely asserting that it is high.
 */
export interface ScoreBreakdown {
    baseline?: number;
    total?: number;
    clamped?: number;
    rank_key?: number;
    edge?: number;
    coverage?: number;
    coverage_band?: string;
    interactions?: number;
    feature_interactions?: number;
    macro_interactions?: number;
    feature_version?: string;
    components?: Record<string, number>;
    /** Per weighted component: did a real observation back it, or was it absent? */
    backed?: Record<string, boolean>;
    funding_rate?: number | null;
    oi_change_pct?: number | null;
    tags?: string[];
}

/**
 * Raw readings the scorer consumed, straight from the persisted feature vector.
 * Every field is optional: older scores predate the flight recorder, and any
 * input can legitimately be missing for a given symbol.
 */
export interface ScoreInputs {
    rsi_1h?: number | null;
    rsi_15m?: number | null;
    rsi_6h?: number | null;
    bb_width_1h?: number | null;
    bb_pct_b_1h?: number | null;
    volume_ratio_1h?: number | null;
    macd_1h?: number | null;
    atr_1h?: number | null;
    ema_trend_6h?: boolean | null;
    rs_vs_btc?: number | null;
    rs_vs_btc_1h?: number | null;
    rs_vs_btc_7d?: number | null;
    ret_1h?: number | null;
    ret_24h?: number | null;
    ret_7d?: number | null;
    l2_buy_vol_2pct?: number | null;
    l2_sell_vol_2pct?: number | null;
    funding_rate?: number | null;
    oi_change_pct?: number | null;
    day_change_pct?: number | null;
    pos_in_range?: number | null;
    quote_vol_24h?: number | null;
    vwap_24h?: number | null;
}

/**
 * Effective scoring config (yaml + persisted overrides).
 *
 * NOTE: `fetchScoringConfig` below returns `any` and is used by `ScoringEditor`,
 * which reads a `components[key].points` shape the backend does not actually
 * return — so that editor silently falls back to its defaults. This typed
 * accessor is deliberately named differently rather than quietly re-pointing the
 * existing one and changing the editor's behaviour as a side effect.
 */
export interface ScoringWeightsConfig {
    baseline: number;
    component_weights: { LONG: Record<string, number>; SHORT: Record<string, number> };
    interaction_bonuses: { confluence_bonus: number; breakout_bonus: number };
    counter_trend_penalty: number;
    macro_beta_penalty: number;
    macro_beta_full_at_pct: number;
}

export async function fetchScoringWeights(): Promise<ScoringWeightsConfig> {
    const res = await apiFetch("/api/v1/config/scoring");
    if (!res.ok) throw new Error(`Scoring config fetch failed: ${res.status}`);
    return res.json();
}

export interface CandidateDrawerPayload {
    product_id: string;
    composite_score: number;
    /** Belief state — see `ScoreBreakdown` for where these come from. */
    edge?: number | null;
    coverage?: number | null;
    coverage_band?: string | null;
    trade_direction?: string;
    label: string;
    ladder: LadderLevels | null;
    features?: FeatureMetrics | null;
    copy_text: string | null;
    /** The scorer's own arithmetic: normalised components + which interactions fired. */
    score_breakdown?: ScoreBreakdown;
    /** Raw readings the scorer consumed, from the persisted feature vector. */
    inputs?: ScoreInputs | null;
    updated_at: string;
    options_flow?: OptionsFlow | Record<string, never> | null;
}

export interface WatchlistItem {
    product_id: string;
    base_currency: string;
    quote_currency: string;
    display_name: string;
    on_watchlist: number;
    active: number;
}

export interface ScanStatus {
    status: "IDLE" | "RUNNING" | "DONE" | "FAILED";
    scan_run_id: string | null;
    started_at?: string;
    completed_at?: string;
    duration_seconds?: number;
    symbols_fetched?: number;
    symbols_stale?: number;
    candidates_count?: number;
}

// ── Market endpoints ──────────────────────────────────────────────────────────

export async function fetchCandidates(): Promise<CandidateRow[]> {
    const res = await apiFetch("/api/v1/markets");
    if (!res.ok) throw new Error(`Candidates fetch failed: ${res.status}`);
    return res.json();
}

export interface HistoricalSetup {
    computed_at: string;
    trade_direction: string;
    composite_score: number;
    label: string;
    tranche_a_price: number;
    tranche_b_price: number;
    stop_price: number;
    target_1_price: number;
    target_2_price?: number | null;
}

export async function fetchMarketLadder(productId: string): Promise<CandidateDrawerPayload> {
    const res = await apiFetch(`/api/v1/markets/${encodeURIComponent(productId)}/ladder`);
    if (!res.ok) throw new Error(`Ladder detail fetch failed: ${res.status}`);
    return res.json();
}

export async function fetchMarketTradeHistory(productId: string): Promise<HistoricalSetup[]> {
    const res = await apiFetch(`/api/v1/markets/${encodeURIComponent(productId)}/trades/history`);
    if (!res.ok) throw new Error(`Trade history fetch failed: ${res.status}`);
    return res.json();
}

// ── Watchlist endpoints ───────────────────────────────────────────────────────

export async function fetchWatchlist(): Promise<WatchlistItem[]> {
    const res = await apiFetch("/api/v1/watchlist");
    if (!res.ok) throw new Error(`Watchlist fetch failed: ${res.status}`);
    return res.json();
}

export async function pinSymbol(productId: string): Promise<{ product_id: string; on_watchlist: boolean }> {
    const res = await apiFetch(`/api/v1/watchlist/${encodeURIComponent(productId)}`, { method: "POST" });
    if (!res.ok) throw new Error(`Pin symbol failed: ${res.status}`);
    return res.json();
}

export async function unpinSymbol(productId: string): Promise<{ product_id: string; on_watchlist: boolean }> {
    const res = await apiFetch(`/api/v1/watchlist/${encodeURIComponent(productId)}`, { method: "DELETE" });
    if (!res.ok) throw new Error(`Unpin symbol failed: ${res.status}`);
    return res.json();
}

// ── Scan endpoints ────────────────────────────────────────────────────────────

export async function triggerScan(): Promise<{ status: string; message: string }> {
    // Backend route is POST /api/v1/scan/start — this previously pointed at a
    // non-existent /scan/trigger path, so the button always 404'd.
    const res = await apiFetch("/api/v1/scan/start", { method: "POST" });
    if (!res.ok) throw new Error(`Scan trigger failed: ${res.status}`);
    return res.json();
}

export async function fetchScanStatus(): Promise<ScanStatus> {
    const res = await apiFetch("/api/v1/scan/status");
    if (!res.ok) throw new Error(`Scan status failed: ${res.status}`);
    return res.json();
}

// ── Config endpoints ─────────────────────────────────────────────────────────

export async function fetchScoringConfig(): Promise<any> {
    const res = await apiFetch("/api/v1/config/scoring");
    if (!res.ok) throw new Error(`Fetch config failed: ${res.status}`);
    return res.json();
}

export async function updateScoringConfig(payload: any): Promise<any> {
    const res = await apiFetch("/api/v1/config/scoring", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
    });
    if (!res.ok) throw new Error(`Update config failed: ${res.status}`);
    return res.json();
}

export async function resetScoringConfig(): Promise<any> {
    const res = await apiFetch("/api/v1/config/scoring", { method: "DELETE" });
    if (!res.ok) throw new Error(`Reset config failed: ${res.status}`);
    return res.json();
}

// ── Alert endpoints ──────────────────────────────────────────────────────────

export interface AlertRow {
    id: string;
    product_id: string;
    alert_type: string;
    price_at_alert: number;
    zone_price: number | null;
    label_at_alert: string | null;
    score_at_alert: number | null;
    created_at: string;
    delivered_at?: string | null;
    suppressed: boolean;
    dismissed_by_user?: boolean;
}

/** Recent alerts, newest first. */
export async function fetchAlerts(page = 1, perPage = 20): Promise<AlertRow[]> {
    const res = await apiFetch(`/api/v1/alerts?page=${page}&per_page=${perPage}`);
    if (!res.ok) throw new Error(`Alerts fetch failed: ${res.status}`);
    return res.json();
}

/** Undelivered alerts (held back by quiet hours). */
export async function fetchPendingAlerts(): Promise<AlertRow[]> {
    const res = await apiFetch("/api/v1/alerts/pending");
    if (!res.ok) throw new Error(`Pending alerts fetch failed: ${res.status}`);
    return res.json();
}

export async function dismissAlert(alertId: string): Promise<{ alert_id: string; dismissed: boolean }> {
    const res = await apiFetch(`/api/v1/alerts/${encodeURIComponent(alertId)}/dismiss`, { method: "PATCH" });
    if (!res.ok) throw new Error(`Dismiss alert failed: ${res.status}`);
    return res.json();
}

// ── Research & Walk-Forward Backtest Endpoints ─────────────────────────────────

export interface SymbolListingBound {
    first_candle_ts: number;
    last_candle_ts: number;
    total_candles: number;
}

export interface ResearchSummaryResponse {
    historical_symbols_count: number;
    total_candles_stored: number;
    symbol_listing_bounds: Record<string, SymbolListingBound>;
    staged_shadow_pipelines: ShadowPipeline[];
    min_shadow_sample_size: number;
    survivorship_bias_note: string;
}

export interface WindowPerformance {
    window_index: number;
    train_start_ts: number;
    train_end_ts: number;
    test_start_ts: number;
    test_end_ts: number;
    trades_count: number;
    win_rate: number;
    avg_r: number;
    max_drawdown_pct: number;
    l2_approximated: boolean;
}

export interface WalkForwardCandidateResult {
    candidate_name: string;
    overall_win_rate: number;
    overall_avg_r: number;
    overall_trades_count: number;
    consistency_score: number;
    window_results: WindowPerformance[];
    l2_approximated: boolean;
    survivorship_bias_note: string;
}

export interface ShadowPipeline {
    pipeline_version: string;
    candidate_name: string;
    staged_at: string;
    sample_count: number;
    target_sample_size: number;
    status: "STAGED" | "ELIGIBLE" | "PROMOTED" | "DISCARDED";
    eligible_for_promotion: boolean;
    win_rate: number;
    promoted_at?: string | null;
}

export async function fetchResearchSummary(): Promise<ResearchSummaryResponse> {
    const res = await apiFetch("/api/v1/research/summary");
    if (!res.ok) throw new Error(`Research summary fetch failed: ${res.status}`);
    return res.json();
}

export async function expandHistory(symbols: string[], years = 5.0): Promise<any> {
    const res = await apiFetch("/api/v1/research/expand-history", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ symbols, years }),
    });
    if (!res.ok) throw new Error(`Expand history failed: ${res.status}`);
    return res.json();
}

export interface StrategyPlugin {
    strategy_id: string;
    name: string;
    description: string;
    author: string;
    version: string;
}

export async function fetchPluggableStrategies(): Promise<{ strategies: StrategyPlugin[]; count: number }> {
    const res = await apiFetch("/api/v1/research/strategies");
    if (!res.ok) throw new Error(`Fetch strategies failed: ${res.status}`);
    return res.json();
}

/**
 * Execute walk-forward backtest research run for candidate strategy validation.
 */
export async function runWalkForwardBacktest(symbols?: string[], strategyId?: string): Promise<{
    candidate_rankings: WalkForwardCandidateResult[];
    symbols_evaluated: string[];
    l2_approximated: boolean;
    survivorship_bias_note: string;
}> {
    const params = new URLSearchParams();
    if (symbols && symbols.length) {
        symbols.forEach((s) => params.append("symbols", s));
    }
    if (strategyId) {
        params.append("strategy_id", strategyId);
    }
    const query = params.toString() ? `?${params.toString()}` : "";
    const res = await apiFetch(`/api/v1/research/run-backtest${query}`, { method: "POST" });
    if (!res.ok) throw new Error(`Run backtest failed: ${res.status}`);
    return res.json();
}

export async function fetchShadowPipelines(): Promise<{
    pipelines: ShadowPipeline[];
    min_shadow_sample_size: number;
}> {
    const res = await apiFetch("/api/v1/research/shadow");
    if (!res.ok) throw new Error(`Fetch shadow pipelines failed: ${res.status}`);
    return res.json();
}

export async function stageCandidateStrategy(candidateName: string, minScore = 60.0): Promise<any> {
    const res = await apiFetch("/api/v1/research/shadow/stage", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ candidate_name: candidateName, min_composite_score: minScore }),
    });
    if (!res.ok) {
        const errJson = await res.json().catch(() => ({ detail: "Stage failed" }));
        throw new Error(errJson.detail || `Stage candidate strategy failed: ${res.status}`);
    }
    return res.json();
}

export async function promoteShadowPipeline(pipelineVersion: string): Promise<any> {
    const res = await apiFetch("/api/v1/research/shadow/promote", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pipeline_version: pipelineVersion, confirm: true }),
    });
    if (!res.ok) {
        const errJson = await res.json().catch(() => ({ detail: "Promotion failed" }));
        throw new Error(errJson.detail || `Promote shadow pipeline failed: ${res.status}`);
    }
    return res.json();
}

