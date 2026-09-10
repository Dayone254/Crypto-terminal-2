"use client";

import React, { useCallback, useEffect, useState } from "react";
import { CandidateRow, fetchCandidates, fetchScanStatus, ScanStatus } from "@/lib/api";
import { Header } from "@/components/Header";
import { MarketScannerTable } from "@/components/MarketScannerTable";
import { WatchlistSidebar } from "@/components/WatchlistSidebar";
import { BacktestLedger } from "@/components/BacktestLedger";
import { TelegramSettings } from "@/components/TelegramSettings";
import { AlertsPanel } from "@/components/AlertsPanel";

export default function DashboardPage() {
    const [candidates, setCandidates] = useState<CandidateRow[]>([]);
    const [scanStatus, setScanStatus] = useState<ScanStatus | null>(null);
    const [refreshKey, setRefreshKey] = useState<number>(0);
    const [toastMessage, setToastMessage] = useState<string | null>(null);

    const loadData = useCallback(async () => {
        try {
            const [candData, statusData] = await Promise.all([
                fetchCandidates(),
                fetchScanStatus(),
            ]);
            setCandidates(candData);
            setScanStatus(statusData);
        } catch (err) {
            console.error("Dashboard data load error:", err);
        }
    }, []);

    useEffect(() => {
        loadData();
        // Poll scan status and candidates every 5 seconds
        const interval = setInterval(loadData, 5000);
        return () => clearInterval(interval);
    }, [loadData]);

    const handleToast = (msg: string) => {
        setToastMessage(msg);
        setTimeout(() => setToastMessage(null), 3000);
    };

    const handlePinToggled = () => {
        loadData();
        setRefreshKey((prev) => prev + 1);
    };

    const pinnedCount = candidates.filter((c) => c.pinned).length;

    return (
        <div style={{ minHeight: "100vh", display: "flex", flexDirection: "column" }}>
            {/* Header */}
            <Header
                status={scanStatus}
                candidateCount={candidates.length}
                pinnedCount={pinnedCount}
                onScanTriggered={loadData}
            />

            {/* Main Content Area */}
            <main style={{ padding: "1.5rem 2rem", flex: 1, display: "grid", gridTemplateColumns: "1fr 280px", gap: "1.5rem" }}>
                {/* Left: Main Market Scanner Table */}
                <MarketScannerTable
                    candidates={candidates}
                    onSelectCandidate={(c) => {
                        window.location.href = `/market/${encodeURIComponent(c.product_id)}`;
                    }}
                    onPinToggled={handlePinToggled}
                />

                {/* Right: Watchlist Sidebar */}
                <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
                    <AlertsPanel />
                    <TelegramSettings />
                    <BacktestLedger />
                    <WatchlistSidebar
                        onSelectSymbol={(sym) => {
                            window.location.href = `/market/${encodeURIComponent(sym)}`;
                        }}
                        refreshKey={refreshKey}
                    />
                </div>
            </main>

            {/* Toast Notification */}
            {toastMessage && (
                <div className="toast">
                    {toastMessage}
                </div>
            )}
        </div>
    );
}
