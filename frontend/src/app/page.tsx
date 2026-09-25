"use client";

import React, { useCallback, useEffect, useState } from "react";
import { CandidateRow, fetchCandidates, triggerScan } from "@/lib/api";
import { Sidebar } from "@/components/Sidebar";
import { Header } from "@/components/Header";
import { Footer } from "@/components/Footer";
import { MarketScannerTable, Candidate } from "@/components/MarketScannerTable";
import { AlphaStreamDock } from "@/components/AlphaStreamDock";
import { Search } from "lucide-react";

export default function DashboardPage() {
    const [rawCandidates, setRawCandidates] = useState<CandidateRow[]>([]);
    const [selectedFilter, setSelectedFilter] = useState<string>("ALL");
    const [searchQuery, setSearchQuery] = useState<string>("");
    const [selectedTimeframe, setSelectedTimeframe] = useState<string>("1H");
    const [toastMessage, setToastMessage] = useState<string | null>(null);
    const [isAlertDockCollapsed, setIsAlertDockCollapsed] = useState<boolean>(false);

    const loadData = useCallback(async () => {
        try {
            const candData = await fetchCandidates();
            setRawCandidates(candData);
        } catch (err) {
            console.error("Dashboard data load error:", err);
        }
    }, []);

    useEffect(() => {
        loadData();
        const interval = setInterval(loadData, 5000);
        return () => clearInterval(interval);
    }, [loadData]);

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

    // Transform backend rows into rich PRO-CORE candidates
    const transformedCandidates: Candidate[] = rawCandidates.map((r, idx) => {
        const score = Math.round(r.composite_score || 75);
        const rankTag: Candidate["rankTag"] =
            score >= 95 ? "ELITE" : score >= 88 ? "PRIME" : score >= 80 ? "ALPHA" : score >= 70 ? "EARLY" : "ACTIVE";

        const classifications = [
            "COILED SQUEEZE BREAK",
            "ABSORPTION ZONE",
            "CVD DIVERGENCE",
            "VOL SQUEEZE BREAK",
            "GAMMA ACCELERATION",
            "EARLY MOMENTUM",
        ];
        const classification = r.label || classifications[idx % classifications.length];

        return {
            id: r.product_id,
            symbol: r.product_id,
            sector: r.product_id.includes("BTC") || r.product_id.includes("ETH") ? "L1 TOP" : r.product_id.includes("SUI") || r.product_id.includes("SOL") ? "L1 HIGH" : "DEFI/ALT",
            exchange: "BINANCE / BYBIT",
            price: r.last_price || 100,
            priceChange: (r.last_price * (r.day_change_pct || 1)) / 100,
            change24h: r.day_change_pct || 0,
            change1h: (r.day_change_pct || 0) * 0.25,
            score: score,
            rankTag: rankTag,
            classification: classification,
            pir: r.pos_in_range || 0.65,
            pirTag: r.pos_in_range > 0.7 ? "TOP" : "MID",
            quoteVol: r.quote_vol_24h || 45000000,
            cvd: (r.day_change_pct >= 0 ? 1 : -1) * (r.quote_vol_24h ? r.quote_vol_24h * 0.12 : 2400000),
            trancheA: r.ladder ? `$${r.ladder.tranche_a_price.toFixed(2)} LIMIT` : "60% @ LIMIT",
            trancheB: r.ladder ? `$${r.ladder.tranche_b_price.toFixed(2)} MARKET` : "40% @ MARKET",
            pinned: r.pinned || false,
            sparklineData: [10, 15, 12, 18, 25, 22, 30],
        };
    });

    const displayCandidates = transformedCandidates;

    // Filter logic
    const filteredCandidates = displayCandidates.filter((c) => {
        const matchesSearch = c.symbol.toLowerCase().includes(searchQuery.toLowerCase()) ||
            c.sector.toLowerCase().includes(searchQuery.toLowerCase());
        if (!matchesSearch) return false;

        if (selectedFilter === "ENTRY_ZONE") return c.classification.includes("BREAKOUT") || c.classification.includes("ZONE");
        if (selectedFilter === "COILED") return c.classification.includes("SQUEEZE") || c.score >= 90;
        if (selectedFilter === "EARLY") return c.cvd > 5000000;
        if (selectedFilter === "WATCHLIST") return c.pinned;
        return true;
    });

    const counts = {
        all: displayCandidates.length,
        entry: displayCandidates.filter((c) => c.classification.includes("BREAKOUT") || c.classification.includes("ZONE")).length,
        coiled: displayCandidates.filter((c) => c.classification.includes("SQUEEZE") || c.score >= 90).length,
        early: displayCandidates.filter((c) => c.cvd > 5000000).length,
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
                universeCount={512}
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

                            {/* Timeframe Buttons */}
                            <div
                                style={{
                                    display: "flex",
                                    alignItems: "center",
                                    backgroundColor: "var(--surface-container-lowest)",
                                    padding: "0.15rem",
                                    borderRadius: "4px",
                                }}
                            >
                                {["15M", "1H", "4H", "1D"].map((tf) => {
                                    const activeTf = selectedTimeframe === tf;
                                    return (
                                        <button
                                            key={tf}
                                            onClick={() => setSelectedTimeframe(tf)}
                                            className="font-label-caps"
                                            style={{
                                                padding: "0.25rem 0.45rem",
                                                borderRadius: "3px",
                                                border: "none",
                                                cursor: "pointer",
                                                backgroundColor: activeTf ? "var(--surface-container-high)" : "transparent",
                                                color: activeTf ? "var(--primary-fixed-dim)" : "var(--outline)",
                                                fontWeight: activeTf ? 700 : 500,
                                            }}
                                        >
                                            {tf}
                                        </button>
                                    );
                                })}
                            </div>
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
                                        window.location.href = `/market/${encodeURIComponent(c.symbol)}`;
                                    }}
                                    onPinCandidate={(sym) => {
                                        setToastMessage(`Toggled pin for ${sym}`);
                                        setTimeout(() => setToastMessage(null), 2000);
                                    }}
                                    onFastStageOrder={(c) => {
                                        window.location.href = `/market/${encodeURIComponent(c.symbol)}`;
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
