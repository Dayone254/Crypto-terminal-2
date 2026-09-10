import React, { useEffect, useRef, useState } from "react";
import { init, dispose, registerOverlay, Chart, KLineData } from "klinecharts";

import { apiFetch, FeatureMetrics, HistoricalSetup, LadderLevels, wsBase } from "@/lib/api";

// Register custom TradingView-style Position Tool overlay (Green Profit Rect + Red Risk Rect)
try {
    registerOverlay({
        name: "positionTool",
        totalStep: 3,
        needDefaultPointFigure: false,
        needDefaultXAxisFigure: false,
        needDefaultYAxisFigure: false,
        createPointFigures: ({ coordinates, bounding }) => {
            if (!coordinates || coordinates.length < 3) return [];

            const startX = coordinates[0]?.x ?? 0;
            const endX = coordinates[1]?.x ?? (startX + 120);

            // Dynamic width matching exact setup duration (TradingView style)
            const rawWidth = endX - startX;
            const width = rawWidth > 0 ? Math.max(40, Math.min(bounding.width - startX - 20, rawWidth)) : Math.max(90, Math.min(240, bounding.width - startX - 30));

            const entryY = coordinates[0]?.y ?? 0;
            const targetY = coordinates[1]?.y ?? entryY;
            const stopY = coordinates[2]?.y ?? entryY;

            // Green Profit Area (between entryY & targetY)
            const profitTop = Math.min(entryY, targetY);
            const profitHeight = Math.max(2, Math.abs(targetY - entryY));

            // Red Risk Area (between entryY & stopY)
            const riskTop = Math.min(entryY, stopY);
            const riskHeight = Math.max(2, Math.abs(stopY - entryY));

            return [
                // Green Profit Zone Rectangle
                {
                    type: "rect",
                    attrs: {
                        x: startX,
                        y: profitTop,
                        width: width,
                        height: profitHeight
                    },
                    styles: {
                        color: "rgba(16, 185, 129, 0.25)",
                        borderColor: "#10B981",
                        borderSize: 1
                    }
                },
                // Red Risk Zone Rectangle
                {
                    type: "rect",
                    attrs: {
                        x: startX,
                        y: riskTop,
                        width: width,
                        height: riskHeight
                    },
                    styles: {
                        color: "rgba(244, 63, 94, 0.25)",
                        borderColor: "#F43F5E",
                        borderSize: 1
                    }
                },
                // TradingView Dotted Diagonal Target Projection Line
                {
                    type: "line",
                    attrs: {
                        coordinates: [{ x: startX, y: entryY }, { x: startX + width, y: targetY }]
                    },
                    styles: {
                        color: "rgba(255, 255, 255, 0.45)",
                        size: 1.5,
                        style: "dashed"
                    }
                },
                // Target Boundary Line (Green)
                {
                    type: "line",
                    attrs: {
                        coordinates: [{ x: startX, y: targetY }, { x: startX + width, y: targetY }]
                    },
                    styles: {
                        color: "#10B981",
                        size: 2,
                        style: "solid"
                    }
                },
                // Entry Boundary Line (White)
                {
                    type: "line",
                    attrs: {
                        coordinates: [{ x: startX, y: entryY }, { x: startX + width, y: entryY }]
                    },
                    styles: {
                        color: "#FFFFFF",
                        size: 1.5,
                        style: "dashed"
                    }
                },
                // Stop Boundary Line (Red)
                {
                    type: "line",
                    attrs: {
                        coordinates: [{ x: startX, y: stopY }, { x: startX + width, y: stopY }]
                    },
                    styles: {
                        color: "#F43F5E",
                        size: 2,
                        style: "solid"
                    }
                }
            ];
        }
    });

    // Register Bookmap-style Orderbook Depth Heatmap Bar Overlay
    registerOverlay({
        name: "l2HeatmapBar",
        totalStep: 2,
        needDefaultPointFigure: false,
        needDefaultXAxisFigure: false,
        needDefaultYAxisFigure: false,
        createPointFigures: ({ coordinates, bounding, overlay }) => {
            if (!coordinates || coordinates.length < 2) return [];

            // Extract custom data (intensity 0-1 and type bid/ask)
            const type = (overlay.extendData as any)?.type || "BID";
            const intensity = (overlay.extendData as any)?.intensity || 0.1;

            const y = coordinates[0]?.y ?? 0;
            const startX = bounding.width - 60; // Mount on the right edge, slightly offset from Y-Axis text

            // Width is proportional to volume intensity
            const width = 60 * intensity;

            const color = type === "ASK" ? `rgba(244, 63, 94, ${intensity * 0.8})` : `rgba(16, 185, 129, ${intensity * 0.8})`;

            return [
                {
                    type: "rect",
                    attrs: {
                        x: startX - width, // Extend leftwards from the axis edge
                        y: y - 2, // 4px thick volume bar
                        width: width,
                        height: 4
                    },
                    styles: {
                        color: color,
                        borderColor: "transparent",
                        borderSize: 0
                    }
                }
            ];
        }
    });

} catch { }

interface NativeChartProps {
    productId: string;
    entryLevel?: number;
    tpLevel?: number;
    slLevel?: number;
    tradeTimestamp?: number;
    features?: FeatureMetrics | null;
    ladder?: LadderLevels | null;
    tradeHistory?: HistoricalSetup[];
    tradeDirection?: string;
    height?: string | number;
}

export const NativeChart: React.FC<NativeChartProps> = ({
    productId,
    entryLevel,
    tpLevel,
    slLevel,
    tradeTimestamp,
    features,
    ladder,
    tradeHistory = [],
    tradeDirection = "LONG",
    height = "650px",
}) => {
    const [granularity, setGranularity] = useState<number>(3600);
    const [isLive, setIsLive] = useState(false);
    const [showHistory, setShowHistory] = useState(false);
    const [currentTool, setCurrentTool] = useState<string | null>(null);
    const [candlesLoadedCount, setCandlesLoadedCount] = useState<number>(0);

    const chartContainerRef = useRef<HTMLDivElement>(null);
    const chartInstance = useRef<Chart | null>(null);
    const lastCandleRef = useRef<KLineData | null>(null);
    const subCallbackRef = useRef<((data: KLineData) => void) | null>(null);

    useEffect(() => {
        if (!chartContainerRef.current) return;

        // Initialize klinecharts v10
        const chart = init(chartContainerRef.current, {
            styles: {
                grid: {
                    show: false,
                    horizontal: { show: false, color: "transparent", size: 0, style: "solid", dashedValue: [] },
                    vertical: { show: false, color: "transparent", size: 0, style: "solid", dashedValue: [] }
                },
                candle: {
                    type: "candle_solid",
                    bar: {
                        upColor: "#10B981",
                        downColor: "#EF4444",
                        noChangeColor: "#64748B",
                        upBorderColor: "#10B981",
                        downBorderColor: "#EF4444",
                        noChangeBorderColor: "#64748B",
                        upWickColor: "#10B981",
                        downWickColor: "#EF4444",
                        noChangeWickColor: "#64748B",
                    },
                    tooltip: {
                        showRule: "follow_cross",
                        showType: "standard"
                    }
                },
                crosshair: {
                    show: true,
                    horizontal: {
                        show: true,
                        line: { show: true, color: "rgba(6, 182, 212, 0.6)", style: "dashed", size: 1 },
                        text: { show: true, color: "#000", backgroundColor: "#06B6D4", size: 11, weight: "bold", paddingLeft: 6, paddingRight: 6, paddingTop: 4, paddingBottom: 4 }
                    },
                    vertical: {
                        show: true,
                        line: { show: true, color: "rgba(6, 182, 212, 0.6)", style: "dashed", size: 1 },
                        text: { show: true, color: "#000", backgroundColor: "#06B6D4", size: 11, weight: "bold", paddingLeft: 6, paddingRight: 6, paddingTop: 4, paddingBottom: 4 }
                    }
                },
                xAxis: {
                    axisLine: { show: true, color: "rgba(255, 255, 255, 0.1)", size: 1 },
                    tickLine: { show: true, color: "rgba(255, 255, 255, 0.1)", size: 1, length: 4 },
                    tickText: { show: true, color: "#64748B", size: 11, family: "sans-serif", weight: "normal", marginStart: 4, marginEnd: 4 }
                },
                yAxis: {
                    axisLine: { show: true, color: "rgba(255, 255, 255, 0.1)", size: 1 },
                    tickLine: { show: true, color: "rgba(255, 255, 255, 0.1)", size: 1, length: 4 },
                    tickText: { show: true, color: "#64748B", size: 11, family: "sans-serif", weight: "normal", marginStart: 4, marginEnd: 4 }
                }
            }
        });

        if (!chart) return;
        chartInstance.current = chart;

        const resizeObserver = new ResizeObserver(() => {
            if (chartInstance.current) {
                chartInstance.current.resize();
            }
        });
        resizeObserver.observe(chartContainerRef.current);

        // Set Symbol & Period
        const periodSpan = granularity >= 86400 ? Math.floor(granularity / 86400) : (granularity >= 3600 ? Math.floor(granularity / 3600) : Math.floor(granularity / 60));
        const periodType = granularity >= 86400 ? "day" : (granularity >= 3600 ? "hour" : "minute");

        chart.setSymbol({ ticker: productId, pricePrecision: 4, volumePrecision: 2 });
        chart.setPeriod({ type: periodType as any, span: periodSpan });

        // Set v10 DataLoader
        chart.setDataLoader({
            getBars: async (params) => {
                const { type, callback } = params;
                if (type === "init" || type === "update") {
                    try {
                        const res = await apiFetch(`/api/v1/markets/${productId}/candles?granularity=${granularity}`);
                        if (!res.ok) {
                            callback([], false);
                            return;
                        }
                        const data: number[][] = await res.json();
                        if (!Array.isArray(data) || data.length === 0) {
                            callback([], false);
                            return;
                        }

                        // Re-sort ascending by timestamp
                        const sortedRaw = [...data].sort((a, b) => a[0] - b[0]);
                        const uniqueRaw = sortedRaw.filter((v, i, a) => i === 0 || v[0] !== a[i - 1][0]);

                        const formatted: KLineData[] = uniqueRaw.map((c) => ({
                            timestamp: Number(c[0]) * 1000,
                            open: Number(c[3]),
                            high: Number(c[2]),
                            low: Number(c[1]),
                            close: Number(c[4]),
                            volume: Number(c[5]) || 0,
                        }));

                        if (formatted.length > 0) {
                            lastCandleRef.current = formatted[formatted.length - 1];
                            setCandlesLoadedCount(prev => prev + 1);
                        }
                        callback(formatted, false);
                    } catch (err) {
                        console.error("Candle fetch error:", err);
                        callback([], false);
                    }
                } else {
                    callback([], false);
                }
            },
            subscribeBar: (params) => {
                subCallbackRef.current = params.callback;
            },
            unsubscribeBar: () => {
                subCallbackRef.current = null;
            }
        });

        // Add Indicators
        (chart as any).createIndicator("EMA", false, { id: "candle_pane" });
        (chart as any).createIndicator("VOL", false, { height: 80 });
        (chart as any).createIndicator("MACD", false, { height: 80 });

        return () => {
            if (chartContainerRef.current) {
                resizeObserver.disconnect();
                dispose(chartContainerRef.current);
            }
            chartInstance.current = null;
            subCallbackRef.current = null;
        };
    }, [productId, granularity]);

    // Reactive Overlays Effect: Re-draw overlays whenever data/ladder/features change
    useEffect(() => {
        const chart = chartInstance.current;
        if (!chart) return;

        // Clear existing overlays to avoid duplicates
        chart.removeOverlay();

        const activeTrancheA = ladder?.tranche_a_price || entryLevel;
        const activeTrancheB = ladder?.tranche_b_price;
        const activeSL = ladder?.stop_price || slLevel;
        const activeTP1 = ladder?.target_1_price || tpLevel;
        const activeTP2 = ladder?.target_2_price;

        const dataList = chart.getDataList();
        const lastCandle = dataList && dataList.length > 0 ? dataList[dataList.length - 1] : null;
        const lastTs = lastCandle ? lastCandle.timestamp : Date.now();

        // Mathematically derive short vs long direction to guarantee green=profit and red=risk
        const isShort = (activeSL && activeTrancheA && activeSL > activeTrancheA) || tradeDirection === "SHORT";
        const entryColor = isShort ? "#F43F5E" : "#06B6D4";
        const tpColor = "#10B981";
        const slColor = isShort ? "#10B981" : "#F43F5E";

        // Main target for position box (use Target 2 if present for full target zone height, else Target 1)
        const mainTP = (activeTP2 && activeTP2 > 0) ? activeTP2 : (activeTP1 || tpLevel);

        // 1. SINGLE ACTIVE / HISTORICAL TRADE SETUP: Render Pristine TradingView Green/Red Position Box Overlay
        if (activeTrancheA && mainTP && activeSL) {
            let startTs: number;
            let futureTs: number;
            const targetMs = tradeTimestamp ? (tradeTimestamp > 1e11 ? tradeTimestamp : tradeTimestamp * 1000) : 0;

            if (targetMs > 0 && dataList && dataList.length > 0) {
                // Find exact or closest candle matching targetMs
                let bestIdx = 0;
                let minDiff = Infinity;
                dataList.forEach((c, idx) => {
                    const diff = Math.abs(c.timestamp - targetMs);
                    if (diff < minDiff) {
                        minDiff = diff;
                        bestIdx = idx;
                    }
                });
                startTs = dataList[bestIdx].timestamp;
                const endIdx = Math.min(dataList.length - 1, bestIdx + 16);
                futureTs = dataList[endIdx].timestamp;
            } else if (targetMs > 0) {
                startTs = targetMs;
                futureTs = startTs + (16 * granularity * 1000);
            } else {
                startTs = lastCandle ? lastCandle.timestamp - (12 * granularity * 1000) : Date.now() - 43200000;
                futureTs = lastTs + (20 * granularity * 1000);
            }

            chart.createOverlay({
                name: "positionTool",
                points: [
                    { timestamp: startTs, value: activeTrancheA },
                    { timestamp: futureTs, value: mainTP },
                    { timestamp: futureTs, value: activeSL }
                ]
            });
        }

        // Note: positionTool overlay handles position box lines & badges.
        // Optional Tranche B / Target 2 helper lines:
        if (activeTrancheB && activeTrancheB > 0) {
            chart.createOverlay({
                name: "horizontalLine",
                points: [{ value: activeTrancheB }],
                styles: { line: { color: "#0EA5E9", style: "dashed", size: 1.5 } }
            });
        }
        if (activeTP2 && activeTP2 > 0) {
            chart.createOverlay({
                name: "horizontalLine",
                points: [{ value: activeTP2 }],
                styles: { line: { color: "#059669", style: "dashed", size: 1.5 } }
            });
        }

        // 2. HISTORICAL TRADE SETUPS: Only render if user toggles showHistory ON
        if (showHistory && tradeHistory && tradeHistory.length > 0) {
            tradeHistory.forEach((hist) => {
                const histTs = new Date(hist.computed_at).getTime();
                const histTarget = (hist.target_2_price && hist.target_2_price > 0) ? hist.target_2_price : hist.target_1_price;

                if (!isNaN(histTs) && hist.tranche_a_price && histTarget && hist.stop_price) {
                    // Compact 4-candle width for historical setup boxes to prevent overlap
                    const histEndTs = histTs + (4 * granularity * 1000);
                    chart.createOverlay({
                        name: "positionTool",
                        points: [
                            { timestamp: histTs, value: hist.tranche_a_price },
                            { timestamp: histEndTs, value: histTarget },
                            { timestamp: histEndTs, value: hist.stop_price }
                        ]
                    });
                }
            });
        }

        // Add Quantitative System Features (7D High, 7D Shelf, VWAP, Fibs)
        if (features) {
            if (features.swing_high_7d && features.swing_high_7d > 0) {
                chart.createOverlay({
                    name: "horizontalLine",
                    points: [{ value: features.swing_high_7d }],
                    styles: { line: { color: "#A855F7", style: "dashed", size: 1 } }
                });
            }
            if (features.swing_shelf_7d && features.swing_shelf_7d > 0) {
                chart.createOverlay({
                    name: "horizontalLine",
                    points: [{ value: features.swing_shelf_7d }],
                    styles: { line: { color: "#C084FC", style: "dashed", size: 1 } }
                });
            }
            if (features.vwap_24h && features.vwap_24h > 0) {
                chart.createOverlay({
                    name: "horizontalLine",
                    points: [{ value: features.vwap_24h }],
                    styles: { line: { color: "#3B82F6", style: "solid", size: 1.5 } }
                });
            }
            if (features.fib_382 && features.fib_382 > 0) {
                chart.createOverlay({
                    name: "horizontalLine",
                    points: [{ value: features.fib_382 }],
                    styles: { line: { color: "#EAB308", style: "dashed", size: 1 } }
                });
            }
            if (features.fib_618 && features.fib_618 > 0) {
                chart.createOverlay({
                    name: "horizontalLine",
                    points: [{ value: features.fib_618 }],
                    styles: { line: { color: "#F59E0B", style: "dashed", size: 1 } }
                });
            }
        }
    }, [productId, entryLevel, tpLevel, slLevel, tradeTimestamp, features, ladder, tradeHistory, tradeDirection, showHistory, granularity, candlesLoadedCount]);

    // Live Data WebSocket (Candles + L2 Orderbook Volumetric Heatmaps)
    useEffect(() => {
        const wsUrl = `${wsBase()}/api/v1/ws/candles/${productId}`;
        const l2Url = `${wsBase()}/api/v1/ws/l2/${productId}`;

        let ws: WebSocket;
        let wsL2: WebSocket;
        let disposed = false;
        let interval: any;
        let lastL2Render = 0;

        const connect = () => {
            ws = new WebSocket(wsUrl);
            wsL2 = new WebSocket(l2Url);

            ws.onopen = () => {
                if (disposed) { ws.close(); return; }
                setIsLive(true);
                interval = setInterval(() => ws.readyState === WebSocket.OPEN && ws.send("ping"), 20000);
            };

            wsL2.onmessage = (e) => {
                if (disposed) return;
                const nowMs = Date.now();
                if (nowMs - lastL2Render < 500) return; // Throttle visual heatmap rendering to 2 FPS max for performance

                try {
                    const l2Data = JSON.parse(e.data);
                    if (chartInstance.current && l2Data.metrics) {
                        lastL2Render = nowMs;
                        chartInstance.current.removeOverlay({ name: "l2HeatmapBar" });

                        // Map top 15 highest liquidity Ask Walls
                        const maxAsk = Math.max(...l2Data.asks.slice(0, 15).map((a: any) => a[2]), 100);
                        l2Data.asks.slice(0, 15).forEach((ask: any) => {
                            const intensity = Math.min(1.0, (ask[2] / maxAsk) * 0.8 + 0.2);
                            chartInstance.current?.createOverlay({
                                name: "l2HeatmapBar",
                                extendData: { type: "ASK", intensity },
                                points: [{ value: ask[0] }]
                            });
                        });

                        // Map top 15 highest liquidity Bid Walls
                        const maxBid = Math.max(...l2Data.bids.slice(0, 15).map((b: any) => b[2]), 100);
                        l2Data.bids.slice(0, 15).forEach((bid: any) => {
                            const intensity = Math.min(1.0, (bid[2] / maxBid) * 0.8 + 0.2);
                            chartInstance.current?.createOverlay({
                                name: "l2HeatmapBar",
                                extendData: { type: "BID", intensity },
                                points: [{ value: bid[0] }]
                            });
                        });
                    }
                } catch { }
            };

            ws.onmessage = (e) => {
                if (disposed) return;
                try {
                    const tick = JSON.parse(e.data);
                    if (!tick.price) return;

                    const priceNum = Number(tick.price);
                    const sizeNum = Number(tick.size) || 0;
                    const now = Math.floor(Date.now() / 1000);
                    const bucketTime = Math.floor(now / granularity) * granularity * 1000;

                    const last = lastCandleRef.current;
                    let nextCandle: KLineData;

                    if (last && last.timestamp === bucketTime) {
                        nextCandle = {
                            ...last,
                            high: Math.max(last.high, priceNum),
                            low: Math.min(last.low, priceNum),
                            close: priceNum,
                            volume: (last.volume || 0) + sizeNum
                        };
                    } else {
                        nextCandle = {
                            timestamp: bucketTime,
                            open: priceNum,
                            high: priceNum,
                            low: priceNum,
                            close: priceNum,
                            volume: sizeNum
                        };
                    }

                    lastCandleRef.current = nextCandle;
                    if (subCallbackRef.current) {
                        subCallbackRef.current(nextCandle);
                    }
                } catch { }
            };

            ws.onclose = () => {
                setIsLive(false);
                clearInterval(interval);
                if (!disposed) setTimeout(connect, 3000);
            };
        };

        connect();
        return () => {
            disposed = true;
            setIsLive(false);
            clearInterval(interval);
            if (ws && ws.readyState === WebSocket.OPEN) ws.close();
            if (wsL2 && wsL2.readyState === WebSocket.OPEN) wsL2.close();
        };
    }, [productId, granularity]);

    const activateDrawingTool = (toolName: string) => {
        if (!chartInstance.current) return;
        if (currentTool === toolName) {
            chartInstance.current.overrideOverlay({ groupId: "drawing" });
            setCurrentTool(null);
        } else {
            chartInstance.current.createOverlay({ name: toolName, groupId: "drawing" });
            setCurrentTool(toolName);
        }
    };

    return (
        <div style={{ position: "relative", width: "100%", display: "flex", flexDirection: "column", gap: "0.5rem" }}>
            {/* Top Control Bar Header */}
            <div style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                background: "#0F172A",
                padding: "0.5rem 0.75rem",
                borderRadius: 0,
                border: "none"
            }}>
                <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
                    {[
                        { label: "15M", val: 900 },
                        { label: "1H", val: 3600 },
                        { label: "6H", val: 21600 },
                        { label: "1D", val: 86400 },
                    ].map((tf) => (
                        <button
                            key={tf.val}
                            onClick={() => setGranularity(tf.val)}
                            style={{
                                background: granularity === tf.val ? "rgba(6, 182, 212, 0.2)" : "rgba(255,255,255,0.05)",
                                border: granularity === tf.val ? "1px solid rgba(6, 182, 212, 0.5)" : "1px solid rgba(255,255,255,0.1)",
                                color: granularity === tf.val ? "#06B6D4" : "var(--text-muted)",
                                padding: "0.35rem 0.65rem",
                                borderRadius: 0,
                                fontSize: "0.65rem",
                                fontWeight: 800,
                                cursor: "pointer",
                                transition: "all 0.15s ease",
                                fontFamily: "var(--font-jetbrains)",
                            }}
                        >
                            {tf.label}
                        </button>
                    ))}

                    <button
                        onClick={() => setShowHistory(!showHistory)}
                        title="Toggle Historical Trade Setup Boxes"
                        style={{
                            background: showHistory ? "rgba(16, 185, 129, 0.2)" : "rgba(255,255,255,0.05)",
                            border: showHistory ? "1px solid rgba(16, 185, 129, 0.5)" : "1px solid rgba(255,255,255,0.1)",
                            color: showHistory ? "#10B981" : "var(--text-muted)",
                            padding: "0.35rem 0.65rem",
                            borderRadius: 0,
                            fontSize: "0.65rem",
                            fontWeight: 800,
                            cursor: "pointer",
                            transition: "all 0.15s ease",
                            fontFamily: "var(--font-jetbrains)",
                            display: "flex",
                            alignItems: "center",
                            gap: "0.3rem"
                        }}
                    >
                        <span>📜</span>
                        <span>{showHistory ? "HISTORY: ON" : "HISTORY: OFF"}</span>
                    </button>
                </div>

                {/* Live dot indicator */}
                <div style={{ display: "flex", alignItems: "center", gap: "0.35rem" }}>
                    <span style={{
                        width: "7px", height: "7px", borderRadius: "50%",
                        background: isLive ? "#10B981" : "#64748B",
                        boxShadow: isLive ? "0 0 6px #10B981" : "none",
                        display: "inline-block",
                        transition: "background 0.3s ease, box-shadow 0.3s ease",
                    }} />
                    <span style={{ fontSize: "0.65rem", fontWeight: 800, color: isLive ? "#10B981" : "#64748B", textTransform: "uppercase", letterSpacing: "0.08em", fontFamily: "var(--font-jetbrains)" }}>
                        {isLive ? "LIVE STREAM" : "OFFLINE"}
                    </span>
                </div>
            </div>

            {/* Chart Canvas Container */}
            <div
                style={{
                    width: "100%",
                    height: typeof height === "number" ? `${height}px` : height,
                    minHeight: "400px",
                    background: "#080A0F",
                    border: "none",
                    borderRadius: 0,
                    overflow: "hidden",
                    position: "relative",
                    resize: "vertical",
                }}
            >
                {/* Drawing Toolbar Overlay */}
                <div style={{ position: "absolute", top: "1rem", left: "1rem", zIndex: 20, display: "flex", flexDirection: "column", gap: "0.4rem", background: "rgba(15, 23, 42, 0.85)", backdropFilter: "blur(4px)", padding: "0.4rem", borderRadius: 0, border: "none" }}>
                    {[
                        { id: "segment", icon: "📏", label: "Trend Line" },
                        { id: "rayLine", icon: "➡️", label: "Ray" },
                        { id: "horizontalLine", icon: "➖", label: "Horiz Line" },
                        { id: "fibonacciLine", icon: "🎯", label: "Fibonacci" }
                    ].map(tool => (
                        <button
                            key={tool.id}
                            title={tool.label}
                            onClick={() => activateDrawingTool(tool.id)}
                            style={{
                                width: "30px", height: "30px",
                                display: "flex", alignItems: "center", justifyContent: "center",
                                background: currentTool === tool.id ? "var(--accent-cyan)" : "transparent",
                                color: currentTool === tool.id ? "#000" : "#FFF",
                                border: "none", cursor: "pointer", borderRadius: 0
                            }}
                        >
                            {tool.icon}
                        </button>
                    ))}
                </div>

                {/* KlineCharts Instance */}
                <div
                    ref={chartContainerRef}
                    style={{ position: "absolute", top: 0, left: 0, right: 0, bottom: 0 }}
                />

                {/* Chart Branding Corner Overlay */}
                <div style={{ position: "absolute", bottom: "1rem", left: "1rem", zIndex: 10, pointerEvents: "none" }}>
                    <div style={{ fontSize: "1.5rem", fontWeight: 800, color: "rgba(255,255,255,0.12)" }}>
                        {productId}
                    </div>
                </div>
            </div>
        </div>
    );
};
