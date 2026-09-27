/**
 * Client-side Stale-While-Revalidate Data Cache Store.
 *
 * Persists API responses in memory and sessionStorage with a 5-minute TTL (300,000 ms).
 * Allows page components to populate instantly on remount without showing blank loading states.
 */

const memoryCache = new Map<string, { data: any; timestamp: number }>();
export const DEFAULT_TTL_MS = 5 * 60 * 1000; // 5 minutes

export function getCachedData<T>(key: string, ttlMs: number = DEFAULT_TTL_MS): T | null {
    const now = Date.now();

    // 1. Check in-memory cache first
    const mem = memoryCache.get(key);
    if (mem && (now - mem.timestamp < ttlMs)) {
        return mem.data as T;
    }

    // 2. Check sessionStorage fallback
    if (typeof window !== "undefined" && window.sessionStorage) {
        try {
            const raw = window.sessionStorage.getItem(`tpt_cache_${key}`);
            if (raw) {
                const parsed = JSON.parse(raw);
                if (parsed && (now - parsed.timestamp < ttlMs)) {
                    // Update memory cache
                    memoryCache.set(key, { data: parsed.data, timestamp: parsed.timestamp });
                    return parsed.data as T;
                }
            }
        } catch { }
    }

    return null;
}

export function setCachedData<T>(key: string, data: T): void {
    const now = Date.now();

    // 1. Save in memory
    memoryCache.set(key, { data, timestamp: now });

    // 2. Save in sessionStorage
    if (typeof window !== "undefined" && window.sessionStorage) {
        try {
            window.sessionStorage.setItem(`tpt_cache_${key}`, JSON.stringify({ data, timestamp: now }));
        } catch { }
    }
}

export function clearCachedData(key?: string): void {
    if (key) {
        memoryCache.delete(key);
        if (typeof window !== "undefined" && window.sessionStorage) {
            try {
                window.sessionStorage.removeItem(`tpt_cache_${key}`);
            } catch { }
        }
    } else {
        memoryCache.clear();
        if (typeof window !== "undefined" && window.sessionStorage) {
            try {
                Object.keys(window.sessionStorage).forEach(k => {
                    if (k.startsWith("tpt_cache_")) window.sessionStorage.removeItem(k);
                });
            } catch { }
        }
    }
}
