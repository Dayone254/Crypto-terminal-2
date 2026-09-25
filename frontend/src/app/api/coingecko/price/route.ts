import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

// 60s in-process cache keyed by query string.
const _cache = new Map<string, { data: unknown; ts: number }>();
const TTL_MS = 60_000;

export async function GET(req: NextRequest) {
    const { searchParams } = req.nextUrl;
    const ids = searchParams.get("ids") ?? "ethereum";
    const vs = searchParams.get("vs_currencies") ?? "btc";
    const cacheKey = `${ids}__${vs}`;
    const now = Date.now();

    const hit = _cache.get(cacheKey);
    if (hit && now - hit.ts < TTL_MS) {
        return NextResponse.json(hit.data);
    }

    try {
        const url = `https://api.coingecko.com/api/v3/simple/price?ids=${ids}&vs_currencies=${vs}`;
        const res = await fetch(url, {
            headers: { Accept: "application/json" },
            next: { revalidate: 60 },
        });
        if (!res.ok) throw new Error(`CoinGecko status ${res.status}`);
        const data = await res.json();
        _cache.set(cacheKey, { data, ts: now });
        return NextResponse.json(data);
    } catch {
        if (hit) return NextResponse.json(hit.data);
        return NextResponse.json({}, { status: 503 });
    }
}
