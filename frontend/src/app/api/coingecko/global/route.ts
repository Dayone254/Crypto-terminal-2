import { NextResponse } from "next/server";

// Cache the response in-memory so we don't burn through CoinGecko rate limits.
// BTC dominance changes slowly — 60s TTL is fine.
let _cache: { data: unknown; ts: number } | null = null;
const TTL_MS = 60_000;

export async function GET() {
    const now = Date.now();
    if (_cache && now - _cache.ts < TTL_MS) {
        return NextResponse.json(_cache.data);
    }
    try {
        const res = await fetch("https://api.coingecko.com/api/v3/global", {
            headers: { Accept: "application/json" },
            // Next.js server-side fetch: no CORS issue.
            next: { revalidate: 60 },
        });
        if (!res.ok) throw new Error(`CoinGecko status ${res.status}`);
        const data = await res.json();
        _cache = { data, ts: now };
        return NextResponse.json(data);
    } catch {
        // Return cached stale data on failure rather than an error.
        if (_cache) return NextResponse.json(_cache.data);
        return NextResponse.json({}, { status: 503 });
    }
}
