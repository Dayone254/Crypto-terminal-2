/** `[price, qty, vol_usd]` */
export type L2Level = [number, number, number];

export interface OrderBookFrame {
    bids: L2Level[];
    asks: L2Level[];
}

export interface L2Wall {
    price: number;
    vol_usd: number;
}

export interface SupportResistanceLevel {
    price: number;
    volume: number;
    strength: number;
}

export interface L2Data extends OrderBookFrame {
    metrics: {
        total_bid_vol_usd: number;
        total_ask_vol_usd: number;
        imbalance_ratio: number;
        buy_walls?: L2Wall[];
        sell_walls?: L2Wall[];
        support_levels?: SupportResistanceLevel[];
        resistance_levels?: SupportResistanceLevel[];
        institutional_bias?: string;
        active_exchanges?: string[];
        total_venues?: number;
    };
}

export function hasOrderBook(data: unknown): data is OrderBookFrame {
    if (!data || typeof data !== "object") return false;
    const d = data as Partial<OrderBookFrame>;
    return Array.isArray(d.bids) && Array.isArray(d.asks);
}

export function isL2Payload(data: unknown): data is L2Data {
    if (!hasOrderBook(data)) return false;
    const m = (data as Partial<L2Data>).metrics;
    return !!m && typeof m.imbalance_ratio === "number";
}

export function isDisabledFrame(data: unknown): boolean {
    if (!data || typeof data !== "object") return false;
    const d = data as { type?: string; error?: string };
    return d.type === "ws_disabled" || d.error === "live_ws_disabled";
}
