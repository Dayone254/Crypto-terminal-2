/**
 * Typed API client for the TPT backend.
 *
 * All backend access goes through this module so the base URL, auth header and
 * WebSocket scheme are defined in exactly one place.
 */

export const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

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

export interface CandidateDrawerPayload {
    product_id: string;
    composite_score: number;
    trade_direction?: string;
    label: string;
    ladder: LadderLevels | null;
    features?: FeatureMetrics | null;
    copy_text: string | null;
    score_breakdown?: any;
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
