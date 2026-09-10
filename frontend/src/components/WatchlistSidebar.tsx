"use client";

import React, { useEffect, useState } from "react";
import { fetchWatchlist, unpinSymbol, WatchlistItem } from "@/lib/api";
import { Bookmark, Star, Trash2 } from "lucide-react";

interface WatchlistSidebarProps {
    onSelectSymbol: (symbol: string) => void;
    refreshKey: number;
}

export const WatchlistSidebar: React.FC<WatchlistSidebarProps> = ({
    onSelectSymbol,
    refreshKey,
}) => {
    const [items, setItems] = useState<WatchlistItem[]>([]);
    const [loading, setLoading] = useState(false);

    const loadWatchlist = () => {
        setLoading(true);
        fetchWatchlist()
            .then(setItems)
            .catch((err) => console.error("Watchlist fetch error:", err))
            .finally(() => setLoading(false));
    };

    useEffect(() => {
        loadWatchlist();
    }, [refreshKey]);

    const handleRemove = async (e: React.MouseEvent, productId: string) => {
        e.stopPropagation();
        try {
            await unpinSymbol(productId);
            loadWatchlist();
        } catch (err) {
            console.error("Unpin error:", err);
        }
    };

    return (
        <div className="glass-panel" style={{ padding: "1rem", display: "flex", flexDirection: "column", gap: "0.75rem", height: "fit-content" }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", borderBottom: "none", paddingBottom: "0.5rem" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                    <Star size={16} color="#F59E0B" fill="#F59E0B" />
                    <h3 style={{ fontSize: "0.85rem", fontWeight: 700, color: "#FFF", textTransform: "uppercase", letterSpacing: "0.03em" }}>
                        Pinned Watchlist ({items.length})
                    </h3>
                </div>
            </div>

            {items.length === 0 ? (
                <p style={{ fontSize: "0.75rem", color: "var(--text-dim)", textAlign: "center", padding: "1rem 0" }}>
                    No pinned symbols. Star any market row to keep priority watch.
                </p>
            ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: "0.4rem" }}>
                    {items.map((item) => (
                        <div
                            key={item.product_id}
                            onClick={() => onSelectSymbol(item.product_id)}
                            style={{
                                display: "flex",
                                alignItems: "center",
                                justifyContent: "space-between",
                                padding: "0.5rem 0.75rem",
                                background: "rgba(255,255,255,0.03)",
                                border: "none",
                                borderRadius: 0,
                                cursor: "pointer",
                                transition: "background 0.15s ease",
                            }}
                            onMouseEnter={(e) => (e.currentTarget.style.background = "var(--panel-hover)")}
                            onMouseLeave={(e) => (e.currentTarget.style.background = "rgba(255,255,255,0.03)")}
                        >
                            <span style={{ fontWeight: 700, fontSize: "0.85rem", color: "#FFF" }}>{item.product_id}</span>
                            <button
                                onClick={(e) => handleRemove(e, item.product_id)}
                                style={{
                                    background: "transparent",
                                    border: "none",
                                    color: "var(--text-dim)",
                                    cursor: "pointer",
                                    padding: "0.2rem",
                                }}
                            >
                                <Trash2 size={14} />
                            </button>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
};
