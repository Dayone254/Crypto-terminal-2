"use client";

import React, { useEffect, useState } from "react";
import { fetchWatchlist, unpinSymbol, WatchlistItem } from "@/lib/api";
import { Bookmark, Star, Trash2, GripVertical } from "lucide-react";

interface WatchlistSidebarProps {
    onSelectSymbol: (symbol: string) => void;
    refreshKey?: number;
}

const STORAGE_KEY = "taperadar_watchlist_order";

export const WatchlistSidebar: React.FC<WatchlistSidebarProps> = ({
    onSelectSymbol,
    refreshKey,
}) => {
    const [items, setItems] = useState<WatchlistItem[]>([]);
    const [loading, setLoading] = useState(false);
    const [draggedIndex, setDraggedIndex] = useState<number | null>(null);
    const [dragOverIndex, setDragOverIndex] = useState<number | null>(null);

    const sortItemsBySavedOrder = (rawItems: WatchlistItem[]): WatchlistItem[] => {
        try {
            const savedOrderJson = localStorage.getItem(STORAGE_KEY);
            if (!savedOrderJson) return rawItems;
            const savedOrder: string[] = JSON.parse(savedOrderJson);

            const orderMap = new Map<string, number>();
            savedOrder.forEach((id, idx) => orderMap.set(id, idx));

            return [...rawItems].sort((a, b) => {
                const rankA = orderMap.has(a.product_id) ? orderMap.get(a.product_id)! : 9999;
                const rankB = orderMap.has(b.product_id) ? orderMap.get(b.product_id)! : 9999;
                return rankA - rankB;
            });
        } catch {
            return rawItems;
        }
    };

    const saveOrder = (newItems: WatchlistItem[]) => {
        try {
            const orderIds = newItems.map((i) => i.product_id);
            localStorage.setItem(STORAGE_KEY, JSON.stringify(orderIds));
        } catch (e) {
            console.error("Failed to save watchlist order:", e);
        }
    };

    const loadWatchlist = () => {
        setLoading(true);
        fetchWatchlist()
            .then((data) => {
                const sorted = sortItemsBySavedOrder(data);
                setItems(sorted);
            })
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

    const handleDragStart = (e: React.DragEvent, index: number) => {
        setDraggedIndex(index);
        e.dataTransfer.effectAllowed = "move";
        e.dataTransfer.setData("text/plain", index.toString());
    };

    const handleDragOver = (e: React.DragEvent, index: number) => {
        e.preventDefault();
        e.dataTransfer.dropEffect = "move";
        if (dragOverIndex !== index) {
            setDragOverIndex(index);
        }
    };

    const handleDrop = (e: React.DragEvent, targetIndex: number) => {
        e.preventDefault();
        if (draggedIndex === null || draggedIndex === targetIndex) {
            setDraggedIndex(null);
            setDragOverIndex(null);
            return;
        }

        const newItems = [...items];
        const [movedItem] = newItems.splice(draggedIndex, 1);
        newItems.splice(targetIndex, 0, movedItem);

        setItems(newItems);
        saveOrder(newItems);
        setDraggedIndex(null);
        setDragOverIndex(null);
    };

    const handleDragEnd = () => {
        setDraggedIndex(null);
        setDragOverIndex(null);
    };

    return (
        <div className="glass-panel" style={{ padding: "1rem", display: "flex", flexDirection: "column", gap: "0.75rem", height: "fit-content" }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", borderBottom: "none", paddingBottom: "0.5rem" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                    <Star size={16} color="var(--warn)" fill="var(--warn)" />
                    <h3 style={{ fontSize: "0.85rem", fontWeight: 700, color: "var(--text-strong)", textTransform: "uppercase", letterSpacing: "0.03em" }}>
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
                    {items.map((item, index) => {
                        const isDragging = draggedIndex === index;
                        const isOver = dragOverIndex === index;

                        return (
                            <div
                                key={item.product_id}
                                draggable
                                onDragStart={(e) => handleDragStart(e, index)}
                                onDragOver={(e) => handleDragOver(e, index)}
                                onDrop={(e) => handleDrop(e, index)}
                                onDragEnd={handleDragEnd}
                                onClick={() => onSelectSymbol(item.product_id)}
                                style={{
                                    display: "flex",
                                    alignItems: "center",
                                    justifyContent: "space-between",
                                    padding: "0.5rem 0.75rem",
                                    background: isOver ? "var(--surface-3)" : "rgba(255,255,255,0.03)",
                                    borderLeft: isOver ? "3px solid var(--info)" : "3px solid transparent",
                                    opacity: isDragging ? 0.4 : 1,
                                    borderRadius: 0,
                                    cursor: "grab",
                                    transition: "background 0.15s ease, border-color 0.15s ease, opacity 0.15s ease",
                                }}
                                onMouseEnter={(e) => {
                                    if (!isDragging) e.currentTarget.style.background = "var(--panel-hover)";
                                }}
                                onMouseLeave={(e) => {
                                    if (!isDragging && !isOver) e.currentTarget.style.background = "rgba(255,255,255,0.03)";
                                }}
                            >
                                <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                                    <GripVertical
                                        size={14}
                                        style={{ color: "var(--text-dim)", cursor: "grab", flexShrink: 0 }}
                                    />
                                    <span style={{ fontWeight: 700, fontSize: "0.85rem", color: "var(--text-strong)", fontFamily: "var(--font-mono)" }}>
                                        {item.product_id}
                                    </span>
                                </div>
                                <button
                                    onClick={(e) => handleRemove(e, item.product_id)}
                                    style={{
                                        background: "transparent",
                                        border: "none",
                                        color: "var(--text-dim)",
                                        cursor: "pointer",
                                        padding: "0.2rem",
                                    }}
                                    title="Unpin symbol"
                                >
                                    <Trash2 size={14} />
                                </button>
                            </div>
                        );
                    })}
                </div>
            )}
        </div>
    );
};
