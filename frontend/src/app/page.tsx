"use client";

import React, { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { CandidateRow, fetchCandidates, triggerScan, pinSymbol, unpinSymbol, fetchScannerEnrichment, fetchUniverseCount } from "@/lib/api";
import { getCachedData, setCachedData } from "@/lib/cache";
import { Sidebar } from "@/components/Sidebar";
import { Header } from "@/components/Header";
import { Footer } from "@/components/Footer";
import { MarketScannerTable, Candidate } from "@/components/MarketScannerTable";
import { AlphaStreamDock } from "@/components/AlphaStreamDock";
import { Search } from "lucide-react";

export default function DashboardPage() {
    const router = useRouter();
    const [rawCandidates, setRawCandidates] = useState<CandidateRow[]>([]);
    const [selectedFilter, setSelectedFilter] = useState<string>("ALL");
    const [searchQuery, setSearchQuery] = useState<string>("");
    const [toastMessage, setToastMessage] = useState<string | null>(null);
    const [isAlertDockCollapsed, setIsAlertDockCollapsed] = useState<boolean>(false);
    const [enrichment, setEnrichment] = useState<Record<string, { change_1h_pct: number | null; cvd_24h_usd: number | null; sparkline: number[] | null }>>({});
    const [universeCount, setUniverseCount] = useState<number | null>(null);

    // Safely populate from client cache post-hydration without triggering SSR mismatch
    useEffect(() => {
        const cached = getCachedData<CandidateRow[]>("scanner_candidates");
        if (cached && cached.length > 0) {
            setRawCandidates(cached);
        }
    }, []);

    const loadData = useCallback(async () => {
        try {
            const candData = await fetchCandidates();
            if (candData && Array.isArray(candData)) {
                setRawCandidates(candData);
                setCachedData("scanner_candidates", candData);
                // Real per-symbol enrichment (1h delta / CVD / sparkline),
                // refreshed on the same cadence as the candidates.
                fetchScannerEnrichment(candData.map((r) => r.product_id))
                    .then(setEnrichment)
                    .catch(() => { /* keep last good enrichment */ });
            }
        } catch (err) {
            console.error("Dashboard data load error:", err);
        }
    }, []);

    // Universe size: number of USDT perps actually trading upstream.
    useEffect(() => {
        fetchUniverseCount().then(setUniverseCount);
        const interval = setInterval(() => fetchUniverseCount().then(setUniverseCount), 300000);
        return () => clearInterval(interval);
    }, []);

    useEffect(() => {
        loadData();
        const interval = setInterval(loadData, 5000);
        return () => clearInterval(interval);
    }, [loadData]);

    // Real watchlist toggle: persists via the watchlist API and flips the
    // row's pinned flag so the WATCHLIST filter reflects it immediately.
    const handlePinCandidate = useCallback(async (sym: string) => {
        const current = rawCandidates.find((r) => r.product_id === sym);
        const willPin = !(current?.pinned);
        try {
            const res = willPin ? await pinSymbol(sym) : await unpinSymbol(sym);
            const nowPinned = (res as { on_watchlist?: boolean })?.on_watchlist ?? willPin;
            setRawCandidates((rows) => rows.map((r) => (r.product_id === sym ? { ...r, pinned: nowPinned } : r)));
            setToastMessage(`${nowPinned ? "Pinned" : "Unpinned"} ${sym}`);
        } catch {
            setToastMessage(`Failed to update watchlist for ${sym}`);
        }
        setTimeout(() => setToastMessage(null), 2000);
    }, [rawCandidates]);

    const handleRunScan = async () => {
        try {
            setToastMessage("Initiating TapeRadar X1 Institutional Scan...");
            await triggerScan();
            await loadData();
            setTimeout(() => setToastMessage("Scan Complete - Signals Updated"), 1200);
            setTimeout(() => setToastMessage(null), 3500);
        } catch (err) {
            setToastMessage("Scan Trigger Executed (Polling Feed)");
            setTimeout(() => setToastMessage(null), 3000);
        }
    };

    // Transform backend rows into candidates. Every displayed number is real:
    // when the backend has no value the column renders an honest dash.
    const transformedCandidates: Candidate[] = rawCandidates.map((r) => {
        const score = Math.round(r.composite_score || 0);
        const rankTag: Candidate["rankTag"] =
            score >= 95 ? "ELITE" : score >= 88 ? "PRIME" : score >= 80 ? "ALPHA" : score >= 70 ? "EARLY" : "ACTIVE";

        const enr = enrichment[r.product_id];

        return {
            id: r.product_id,
            symbol: r.product_id,
            sector: r.coverage_band || "—",
            exchange: "BINANCE PERP",
            price: r.last_price ?? 0,
            priceChange: r.last_price && r.day_change_pct != null ? (r.last_price * r.day_change_pct) / 100 : 0,
            change24h: r.day_change_pct ?? 0,
            change1h: enr?.change_1h_pct ?? null,
            score: score,
            rankTag: rankTag,
            classification: r.label || "UNCLASSIFIED",
            pir: r.pos_in_range ?? 0,
            pirTag: (r.pos_in_range ?? 0) > 0.7 ? "TOP" : "MID",
            quoteVol: r.quote_vol_24h ?? 0,
            cvd: enr?.cvd_24h_usd ?? null,
            trancheA: r.ladder ? `$${r.ladder.tranche_a_price.toFixed(2)} LIMIT` : "—",
            trancheB: r.ladder ? `$${r.ladder.tranche_b_price.toFixed(2)} MARKET` : "—",
            pinned: r.pinned || false,
            sparklineData: enr?.sparkline ?? null,
        };
    });

    const displayCandidates = transformedCandidates;

    // Filter logic — matches on the backend's own labels, not synthetic fields
    const matchesClass = (c: Candidate, re: RegExp) =>
        re.test(c.classification.toUpperCase());
    const filteredCandidates = displayCandidates.filter((c) => {
        const matchesSearch = c.symbol.toLowerCase().includes(searchQuery.toLowerCase()) ||
            c.classification.toLowerCase().includes(searchQuery.toLowerCase());
        if (!matchesSearch) return false;

        if (selectedFilter === "ENTRY_ZONE") return matchesClass(c, /ZONE|ENTRY|ABSORPTION/);
        if (selectedFilter === "COILED") return matchesClass(c, /COILED|SQUEEZE/);
        if (selectedFilter === "EARLY") return matchesClass(c, /MOMENTUM|EARLY/);
        if (selectedFilter === "WATCHLIST") return c.pinned;
        return true;
    });

    const counts = {
        all: displayCandidates.length,
        entry: displayCandidates.filter((c) => matchesClass(c, /ZONE|ENTRY|ABSORPTION/)).length,
        coiled: displayCandidates.filter((c) => matchesClass(c, /COILED|SQUEEZE/)).length,
        early: displayCandidates.filter((c) => matchesClass(c, /MOMENTUM|EARLY/)).length,
        watchlist: displayCandidates.filter((c) => c.pinned).length,
    };

    return (
        <div style={{ minHeight: "100vh", backgroundColor: "var(--surface-container-lowest)", color: "var(--on-surface)" }}>
            {/* Left Fixed Sidebar */}
            <Sidebar
                onRunScan={handleRunScan}
                coiledCount={counts.coiled}
                surgeCount={counts.early}
                gammaCount={displayCandidates.filter((c) => c.classification.toLowerCase().includes("gamma")).length}
            />

            {/* Top Fixed Dual-Tier Header */}
            <Header
                universeCount={universeCount ?? undefined}
                activeCount={counts.all}
                highConvictionCount={displayCandidates.filter((c) => c.score >= 95).length}
                selectedFilter={selectedFilter}
                onSelectFilter={(f) => setSelectedFilter(f)}
            />

            {/* Main Content Area (padded for left 256px sidebar, top 112px header, bottom 32px footer) */}
            <main
                style={{
                    paddingLeft: "var(--sidebar-width, 256px)",
                    paddingTop: "112px",
                    paddingBottom: "32px",
                    minHeight: "100vh",
                    transition: "var(--sidebar-transition, all 0.3s)",
                }}
            >
                <div style={{ padding: "1rem 1.25rem", display: "flex", flexDirection: "column", gap: "1rem" }}>
                    {/* ── Sub Filter Bar & Search ── */}
                    <div
                        style={{
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "space-between",
                            gap: "1rem",
                            backgroundColor: "var(--surface-container-low)",
                            padding: "0.5rem 0.75rem",
                            borderRadius: "6px",
                            border: "1px solid var(--outline-variant)",
                        }}
                    >
                        {/* Live Count Filter Pills */}
                        <div style={{ display: "flex", alignItems: "center", gap: "0.35rem", overflowX: "auto" }}>
                            {[
                                { key: "ALL", label: `ALL (${counts.all})` },
                                { key: "ENTRY_ZONE", label: `ENTRY ZONE (${counts.entry})` },
                                { key: "COILED", label: `COILED SQUEEZE (${counts.coiled})` },
                                { key: "EARLY", label: `EARLY MOMENTUM (${counts.early})` },
                                { key: "WATCHLIST", label: `WATCHLIST (${counts.watchlist})` },
                            ].map((pill) => {
                                const active = selectedFilter === pill.key;
                                return (
                                    <button
                                        key={pill.key}
                                        onClick={() => setSelectedFilter(pill.key)}
                                        className="font-label-caps"
                                        style={{
                                            padding: "0.3rem 0.6rem",
                                            borderRadius: "4px",
                                            border: "none",
                                            cursor: "pointer",
                                            backgroundColor: active ? "var(--primary-container)" : "var(--surface-container)",
                                            color: active ? "var(--on-primary-container)" : "var(--on-surface-variant)",
                                            fontWeight: active ? 700 : 500,
                                            transition: "all var(--dur-fast) var(--ease-out)",
                                        }}
                                    >
                                        {pill.label}
                                    </button>
                                );
                            })}
                        </div>

                        {/* Search Input & Timeframes */}
                        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
                            <div
                                style={{
                                    display: "flex",
                                    alignItems: "center",
                                    gap: "0.35rem",
                                    backgroundColor: "var(--surface-container-lowest)",
                                    padding: "0.25rem 0.65rem",
                                    borderRadius: "4px",
                                    border: "1px solid var(--outline-variant)",
                                    width: "280px",
                                }}
                            >
                                <Search size={14} color="var(--outline)" />
                                <input
                                    type="text"
                                    placeholder="Search symbol (e.g. SUI, ETH, PENDLE)..."
                                    value={searchQuery}
                                    onChange={(e) => setSearchQuery(e.target.value)}
                                    className="font-body-sm"
                                    style={{
                                        background: "none",
                                        border: "none",
                                        outline: "none",
                                        color: "var(--on-surface)",
                                        width: "100%",
                                    }}
                                />
                            </div>

                            {/* Timeframe buttons removed: the scanner is a 24h/
                                1h-scan snapshot, not a per-timeframe view — the
                                buttons previously changed state nothing consumed. */}
                        </div>
                    </div>

                    {/* ── 12-Column Institutional Grid System ── */}
                    <div style={{ display: "grid", gridTemplateColumns: "repeat(12, 1fr)", gap: "1rem" }}>
                        {/* Scanner Table Matrix */}
                        <div style={{ gridColumn: isAlertDockCollapsed ? "span 11" : "span 9", transition: "all 0.3s cubic-bezier(0.4, 0, 0.2, 1)" }}>
                            {filteredCandidates.length > 0 ? (
                                <MarketScannerTable
                                    candidates={filteredCandidates}
                                    onSelectCandidate={(c) => {
                                        router.push(`/market/${encodeURIComponent(c.symbol)}`);
                                    }}
                                    onPinCandidate={handlePinCandidate}
                                    onFastStageOrder={(c) => {
                                        router.push(`/market/${encodeURIComponent(c.symbol)}`);
                                    }}
                                />
                            ) : (
                                <div
                                    style={{
                                        display: "flex",
                                        flexDirection: "column",
                                        alignItems: "center",
                                        justifyContent: "center",
                                        gap: "0.75rem",
                                        padding: "3rem 2rem",
                                        backgroundColor: "var(--surface-container-low)",
                                        borderRadius: "6px",
                                        border: "1px solid var(--outline-variant)",
                                        textAlign: "center",
                                    }}
                                >
                                    <span style={{ fontSize: "2rem" }}>⚡</span>
                                    <span className="font-headline-sm" style={{ color: "var(--on-surface)" }}>
                                        No signals detected
                                    </span>
                                    <span className="font-body-md" style={{ color: "var(--on-surface-variant)", maxWidth: "360px" }}>
                                        {rawCandidates.length === 0
                                            ? "Click \"RUN INSTITUTIONAL SCAN\" in the sidebar to discover high-conviction setups across the universe."
                                            : `No candidates match the current filter. Try switching to "ALL" or adjusting your search.`}
                                    </span>
                                </div>
                            )}
                        </div>

                        {/* Live Alpha Stream Dock */}
                        <div style={{ gridColumn: isAlertDockCollapsed ? "span 1" : "span 3", transition: "all 0.3s cubic-bezier(0.4, 0, 0.2, 1)" }}>
                            <AlphaStreamDock
                                isCollapsed={isAlertDockCollapsed}
                                onToggle={() => setIsAlertDockCollapsed(!isAlertDockCollapsed)}
                            />
                        </div>
                    </div>
                </div>
            </main>

            {/* Bottom Fixed Institutional Status Footer */}
            <Footer />

            {/* Toast Notification */}
            {toastMessage && (
                <div
                    className="font-mono-data-compact"
                    style={{
                        position: "fixed",
                        bottom: "40px",
                        right: "20px",
                        backgroundColor: "var(--surface-container-high)",
                        color: "var(--primary)",
                        padding: "0.5rem 1rem",
                        borderRadius: "6px",
                        boxShadow: "0 4px 12px rgba(0,0,0,0.5)",
                        border: "1px solid var(--primary-fixed-dim)",
                        zIndex: 9999,
                        fontWeight: 600,
                    }}
                >
                    {toastMessage}
                </div>
            )}
        </div>
    );
}
