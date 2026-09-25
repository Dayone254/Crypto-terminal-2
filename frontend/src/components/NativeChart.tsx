import React, { useEffect, useRef, useState } from "react";
import { init, dispose, registerOverlay, Chart, KLineData } from "klinecharts";
import {
    Activity,
    ArrowRight,
    BarChart2,
    Check,
    ChevronDown,
    Eye,
    Layers,
    Maximize2,
    Minimize2,
    Minus,
    MousePointer2,
    Pencil,
    RotateCcw,
    Sliders,
    Sparkles,
    TrendingUp,
    Zap,
} from "lucide-react";

import { apiFetch, FeatureMetrics, HistoricalSetup, LadderLevels, wsBase } from "@/lib/api";
import { CANDLE_COLORS, CHART_COLORS } from "@/lib/chartColors";
import { hasOrderBook, isDisabledFrame } from "@/lib/l2";

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

            const rawWidth = endX - startX;
            const width = rawWidth > 0 ? Math.max(40, Math.min(bounding.width - startX - 20, rawWidth)) : Math.max(90, Math.min(240, bounding.width - startX - 30));

            const entryY = coordinates[0]?.y ?? 0;
            const targetY = coordinates[1]?.y ?? entryY;
            const stopY = coordinates[2]?.y ?? entryY;

            const profitTop = Math.min(entryY, targetY);
            const profitHeight = Math.max(2, Math.abs(targetY - entryY));

            const riskTop = Math.min(entryY, stopY);
            const riskHeight = Math.max(2, Math.abs(stopY - entryY));

            return [
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
                        borderColor: CHART_COLORS.pos,
                        borderSize: 1
                    }
                },
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
                        borderColor: CHART_COLORS.neg,
                        borderSize: 1
                    }
                },
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
                {
                    type: "line",
                    attrs: {
                        coordinates: [{ x: startX, y: targetY }, { x: startX + width, y: targetY }]
                    },
                    styles: {
                        color: CHART_COLORS.pos,
                        size: 2,
                        style: "solid"
                    }
                },
                {
                    type: "line",
                    attrs: {
                        coordinates: [{ x: startX, y: entryY }, { x: startX + width, y: entryY }]
                    },
                    styles: {
                        color: CHART_COLORS.textStrong,
                        size: 1.5,
                        style: "dashed"
                    }
                },
                {
                    type: "line",
                    attrs: {
                        coordinates: [{ x: startX, y: stopY }, { x: startX + width, y: stopY }]
                    },
                    styles: {
                        color: CHART_COLORS.neg,
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
        totalStep: 1,
        needDefaultPointFigure: false,
        needDefaultXAxisFigure: false,
        needDefaultYAxisFigure: false,
        createPointFigures: ({ coordinates, bounding, overlay }) => {
            return [];
        }
    });

    // Register Price Level Line Overlay with Right-Axis Label Tag
    registerOverlay({
        name: "priceLevelTagLine",
        totalStep: 1,
        needDefaultPointFigure: false,
        needDefaultXAxisFigure: false,
        needDefaultYAxisFigure: false,
        createPointFigures: ({ coordinates, bounding, overlay }) => {
            if (!coordinates || coordinates.length < 1) return [];
            const y = coordinates[0]?.y ?? 0;
            if (isNaN(y) || y <= 0) return [];

            const label = (overlay.extendData as any)?.label || "";
            const color = (overlay.extendData as any)?.color || "#06b6d4";
            const tagBg = (overlay.extendData as any)?.tagBg || color;

            const labelWidth = Math.max(80, label.length * 7 + 16);
            const tagX = 85; // Shifted right to perfectly clear the Glassmorphism Drawing Toolbar

            return [
                {
                    type: "line",
                    attrs: {
                        coordinates: [{ x: 0, y }, { x: bounding.width, y }]
                    },
                    styles: {
                        color: color,
                        size: 1.5,
                        style: "dashed"
                    }
                },
                {
                    type: "rect",
                    attrs: {
                        x: tagX,
                        y: y - 11,
                        width: labelWidth + 8,
                        height: 22,
                        r: 3
                    },
                    styles: {
                        color: tagBg,
                        style: "fill"
                    }
                },
                {
                    type: "text",
                    attrs: {
                        x: tagX + labelWidth / 2,
                        y: y + 1,
                        text: label,
                        align: "center",
                        baseline: "middle"
                    },
                    styles: {
                        color: "#ffffff",
                        size: 14,
                        weight: "bold",
                        family: "sans-serif"
                    }
                }
            ];
        }
    });

    // Register GEX Liquidity Zone Overlay (Intensity-Based Height Band + Edge-Pinned Tags)
    registerOverlay({
        name: "gexLiquidityZone",
        totalStep: 1,
        needDefaultPointFigure: false,
        needDefaultXAxisFigure: false,
        needDefaultYAxisFigure: false,
        createPointFigures: ({ coordinates, bounding, overlay }) => {
            if (!coordinates || coordinates.length < 1) return [];
            const rawY = coordinates[0]?.y;
            if (rawY === undefined || rawY === null || isNaN(rawY)) return [];

            const label = (overlay.extendData as any)?.label || "";
            const fillColor = (overlay.extendData as any)?.fillColor || "rgba(244, 63, 94, 0.20)";
            const borderColor = (overlay.extendData as any)?.borderColor || "#f43f5e";
            const tagBg = (overlay.extendData as any)?.tagBg || borderColor;
            const height = (overlay.extendData as any)?.height || 14;
            const isDashed = (overlay.extendData as any)?.isDashed || false;

            const isAbove = rawY < 0;
            const isBelow = rawY > bounding.height;
            const isVisible = !isAbove && !isBelow;

            // Clamp Y position for edge pinning when off-screen
            const tagY = isAbove ? 16 : (isBelow ? Math.max(16, bounding.height - 24) : rawY);
            const prefix = isAbove ? "▲ " : (isBelow ? "▼ " : "");
            const displayLabel = `${prefix}${label}`;

            const labelWidth = Math.max(100, displayLabel.length * 7 + 16);
            const tagX = Math.max(10, bounding.width - labelWidth - 85);
            const topY = rawY - height / 2;

            const figures: any[] = [];

            // 1. Shaded Intensity Band Across Canvas
            if (isVisible && height > 2) {
                figures.push({
                    type: "rect",
                    attrs: {
                        x: 0,
                        y: topY,
                        width: bounding.width,
                        height: height,
                    },
                    styles: {
                        color: fillColor,
                        style: "fill"
                    }
                });
            }

            // 2. Center Strike Line
            if (isVisible) {
                figures.push({
                    type: "line",
                    attrs: {
                        coordinates: [{ x: 0, y: rawY }, { x: bounding.width, y: rawY }]
                    },
                    styles: {
                        color: borderColor,
                        size: isDashed ? 1.5 : 2,
                        style: isDashed ? "dashed" : "solid"
                    }
                });
            }

            // 3. Tag Badge Box (Edge Pinned if Off-Screen)
            figures.push({
                type: "rect",
                attrs: {
                    x: tagX,
                    y: tagY - 11,
                    width: labelWidth,
                    height: 22,
                    r: 4
                },
                styles: {
                    color: tagBg,
                    style: "fill"
                }
            });

            // 4. Tag Text
            figures.push({
                type: "text",
                attrs: {
                    x: tagX + labelWidth / 2,
                    y: tagY + 1,
                    text: displayLabel,
                    align: "center",
                    baseline: "middle"
                },
                styles: {
                    color: "#ffffff",
                    size: 12,
                    weight: "bold",
                    family: "sans-serif"
                }
            });

            return figures;
        }
    });
} catch { }

export interface NativeChartProps {
    productId: string;
    entryLevel?: number;
    tpLevel?: number;
    slLevel?: number;
    tradeTimestamp?: number;
    features?: FeatureMetrics | null;
    ladder?: LadderLevels | null;
    optionsFlow?: any;
    tradeHistory?: HistoricalSetup[];
    tradeDirection?: string;
    height?: string | number;
}

// Indicator Options Definition
const MAIN_INDICATOR_OPTIONS = [
    { name: "EMA", label: "EMA (20/50/200)", color: CHART_COLORS.ema20 },
    { name: "SMA", label: "SMA (Moving Average)", color: CHART_COLORS.sma },
    { name: "BOLL", label: "Bollinger Bands", color: CHART_COLORS.bollUpper },
    { name: "SAR", label: "Parabolic SAR", color: CHART_COLORS.warnBright },
    { name: "BBI", label: "Bull/Bear Index", color: CHART_COLORS.purpleBright },
];

const SUB_INDICATOR_OPTIONS = [
    { name: "VOL", label: "Volume + MA", color: CHART_COLORS.info },
    { name: "RSI", label: "RSI (14)", color: CHART_COLORS.rsiLine },
    { name: "MACD", label: "MACD (12, 26, 9)", color: CHART_COLORS.macdLine },
    { name: "KDJ", label: "Stochastic KDJ", color: CHART_COLORS.sky },
    { name: "ATR", label: "Average True Range", color: CHART_COLORS.warn },
    { name: "OBV", label: "On Balance Volume", color: CHART_COLORS.pos },
    { name: "WR", label: "Williams %R", color: CHART_COLORS.purple },
    { name: "CCI", label: "Commodity Channel Index", color: CHART_COLORS.blueBright },
];

const STRATEGY_PRESETS = [
    { id: "SCALP", name: "⚡ Scalp", main: ["EMA"], sub: ["VOL", "RSI"] },
    { id: "TREND", name: "📊 Trend", main: ["BOLL"], sub: ["VOL", "MACD"] },
    { id: "QUANT", name: "🎯 Quant", main: ["EMA", "BOLL"], sub: ["VOL", "RSI", "MACD"] },
    { id: "CLEAN", name: "🧹 Clean", main: [], sub: ["VOL"] },
];

export const NativeChart: React.FC<NativeChartProps> = ({
    productId,
    entryLevel,
    tpLevel,
    slLevel,
    tradeTimestamp,
    features,
    ladder,
    optionsFlow,
    tradeHistory = [],
    tradeDirection = "LONG",
    height = "650px",
}) => {
    const [granularity, setGranularity] = useState<number>(3600);
    const [isLive, setIsLive] = useState(false);
    const [showHistory, setShowHistory] = useState(false);
    const [showHeatmap, setShowHeatmap] = useState(true);
    const [showGexZones, setShowGexZones] = useState(true);
    const [gexData, setGexData] = useState<any>(optionsFlow || null);
    const [currentTool, setCurrentTool] = useState<string | null>(null);
    const [candlesLoadedCount, setCandlesLoadedCount] = useState<number>(0);
    const [isFullscreen, setIsFullscreen] = useState(false);
    const [candleType, setCandleType] = useState<"candle_solid" | "ohlc" | "area">("candle_solid");

    // Indicators state
    const [activeMainIndicators, setActiveMainIndicators] = useState<string[]>(["EMA"]);
    const [activeSubIndicators, setActiveSubIndicators] = useState<string[]>(["VOL", "RSI"]);
    const [showIndicatorMenu, setShowIndicatorMenu] = useState(false);
    const [showPresetMenu, setShowPresetMenu] = useState(false);

    // Fetch / Sync live GEX data for the active symbol
    useEffect(() => {
        if (optionsFlow) {
            setGexData(optionsFlow);
        }

        let isMounted = true;
        const fetchGex = () => {
            apiFetch(`/api/v1/options/flow/${productId}`)
                .then(res => res.ok ? res.json() : null)
                .then(data => {
                    if (isMounted && data) {
                        setGexData(data);
                    }
                })
                .catch(() => { });
        };

        fetchGex();
        const interval = setInterval(fetchGex, 15000);

        return () => {
            isMounted = false;
            clearInterval(interval);
        };
    }, [productId, optionsFlow]);

    const chartContainerRef = useRef<HTMLDivElement>(null);
    const chartWrapperRef = useRef<HTMLDivElement>(null);
    const chartInstance = useRef<Chart | null>(null);
    const lastCandleRef = useRef<KLineData | null>(null);
    const oldestCandleRef = useRef<number | null>(null);
    const subCallbackRef = useRef<((data: KLineData) => void) | null>(null);
    const subPaneIdsRef = useRef<string[]>([]);

    useEffect(() => {
        if (!chartContainerRef.current) return;

        // Reset candle refs whenever symbol or timeframe (granularity) changes
        oldestCandleRef.current = null;
        lastCandleRef.current = null;

        // Initialize klinecharts v10
        const chart = init(chartContainerRef.current, {
            styles: {
                grid: {
                    show: true,
                    horizontal: { show: true, color: "rgba(255, 255, 255, 0.04)", size: 1, style: "dashed", dashedValue: [2, 2] },
                    vertical: { show: true, color: "rgba(255, 255, 255, 0.04)", size: 1, style: "dashed", dashedValue: [2, 2] }
                },
                candle: {
                    type: candleType,
                    bar: {
                        upColor: CANDLE_COLORS.up,
                        downColor: CANDLE_COLORS.down,
                        noChangeColor: CANDLE_COLORS.noChange,
                        upBorderColor: CANDLE_COLORS.up,
                        downBorderColor: CANDLE_COLORS.down,
                        noChangeBorderColor: CANDLE_COLORS.noChange,
                        upWickColor: CANDLE_COLORS.up,
                        downWickColor: CANDLE_COLORS.down,
                        noChangeWickColor: CANDLE_COLORS.noChange,
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
                        text: { show: true, color: CHART_COLORS.textInverse, backgroundColor: CHART_COLORS.info, size: 13, weight: "bold", paddingLeft: 8, paddingRight: 8, paddingTop: 6, paddingBottom: 6 }
                    },
                    vertical: {
                        show: true,
                        line: { show: true, color: "rgba(6, 182, 212, 0.6)", style: "dashed", size: 1 },
                        text: { show: true, color: CHART_COLORS.textInverse, backgroundColor: CHART_COLORS.info, size: 13, weight: "bold", paddingLeft: 8, paddingRight: 8, paddingTop: 6, paddingBottom: 6 }
                    }
                },
                xAxis: {
                    axisLine: { show: true, color: "rgba(255, 255, 255, 0.1)", size: 1 },
                    tickLine: { show: true, color: "rgba(255, 255, 255, 0.1)", size: 1, length: 4 },
                    tickText: { show: true, color: CHART_COLORS.text4, size: 12, family: "sans-serif", weight: "normal", marginStart: 4, marginEnd: 4 }
                },
                yAxis: {
                    axisLine: { show: true, color: "rgba(255, 255, 255, 0.1)", size: 1 },
                    tickLine: { show: true, color: "rgba(255, 255, 255, 0.1)", size: 1, length: 4 },
                    tickText: { show: true, color: CHART_COLORS.text4, size: 13, family: "sans-serif", weight: "normal", marginStart: 4, marginEnd: 4 }
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

        const periodSpan = granularity >= 86400 ? Math.floor(granularity / 86400) : (granularity >= 3600 ? Math.floor(granularity / 3600) : Math.floor(granularity / 60));
        const periodType = granularity >= 86400 ? "day" : (granularity >= 3600 ? "hour" : "minute");

        chart.setSymbol({ ticker: productId, pricePrecision: 4, volumePrecision: 2 });
        chart.setPeriod({ type: periodType as any, span: periodSpan });

        chart.setDataLoader({
            getBars: async (params: any) => {
                const { type, callback } = params;
                // Safely grab the oldest known candle from the chart's internal buffer
                const dataList = chartInstance.current?.getDataList() || [];
                const oldestTs = dataList.length > 0 ? dataList[0].timestamp : null;

                if (type === "init" || type === "update") {
                    // Initial load: request 1000 candles (DB history + live fill-gap)
                    try {
                        const res = await apiFetch(
                            `/api/v1/markets/${productId}/candles?granularity=${granularity}&limit=1000`
                        );
                        if (!res.ok) {
                            callback([], false);
                            return;
                        }
                        const data: number[][] = await res.json();
                        if (!Array.isArray(data) || data.length === 0) {
                            callback([], false);
                            return;
                        }

                        const sortedRaw = [...data].sort((a, b) => a[0] - b[0]);
                        const uniqueRaw = sortedRaw.filter((v, i, a) => i === 0 || v[0] !== a[i - 1][0]);

                        const formatted: KLineData[] = uniqueRaw.map((c) => ({
                            timestamp: Number(c[0]) * 1000,
                            open: Number(c[1]),
                            high: Number(c[2]),
                            low: Number(c[3]),
                            close: Number(c[4]),
                            volume: Number(c[5]) || 0,
                        }));

                        if (formatted.length > 0) {
                            lastCandleRef.current = formatted[formatted.length - 1];
                            if (!oldestCandleRef.current || formatted[0].timestamp < oldestCandleRef.current) {
                                oldestCandleRef.current = formatted[0].timestamp;
                            }
                            setCandlesLoadedCount(prev => prev + 1);
                        }
                        // noMore=false → chart knows it can request more when scrolling left
                        callback(formatted, formatted.length < 10);
                    } catch (err) {
                        console.error("Candle fetch error:", err);
                        callback([], false);
                    }
                } else if (type === "loaded") {
                    const oldestTs = oldestCandleRef.current;
                    if (!oldestTs) {
                        console.error("klinecharts tried to load more but oldest timestamp is missing!");
                        callback([], true);
                        return;
                    }
                    // Scroll-left pagination: fetch candles older than what's already on screen
                    try {
                        const beforeTsSec = Math.floor(oldestTs / 1000);
                        const res = await apiFetch(
                            `/api/v1/markets/${productId}/candles?granularity=${granularity}&limit=1000&before_ts=${beforeTsSec}`
                        );
                        if (!res.ok) {
                            callback([], true);
                            return;
                        }
                        const data: number[][] = await res.json();
                        if (!Array.isArray(data) || data.length === 0) {
                            callback([], true);  // noMore=true → stop requesting
                            return;
                        }

                        const sortedRaw = [...data].sort((a, b) => a[0] - b[0]);
                        const uniqueRaw = sortedRaw.filter((v, i, a) => i === 0 || v[0] !== a[i - 1][0]);

                        const formatted: KLineData[] = uniqueRaw.map((c) => ({
                            timestamp: Number(c[0]) * 1000,
                            open: Number(c[1]),
                            high: Number(c[2]),
                            low: Number(c[3]),
                            close: Number(c[4]),
                            volume: Number(c[5]) || 0,
                        })).filter(c => c.timestamp < oldestTs);

                        if (formatted.length > 0) {
                            if (!oldestCandleRef.current || formatted[0].timestamp < oldestCandleRef.current) {
                                oldestCandleRef.current = formatted[0].timestamp;
                            }
                        }

                        callback(formatted, formatted.length < 10);
                    } catch (err) {
                        console.error("Candle scroll-left error:", err);
                        callback([], true);
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

        return () => {
            if (chartContainerRef.current) {
                resizeObserver.disconnect();
                dispose(chartContainerRef.current);
            }
            chartInstance.current = null;
            subCallbackRef.current = null;
            subPaneIdsRef.current = [];
        };
    }, [productId, granularity]);

    // Candle type updates
    useEffect(() => {
        const chart = chartInstance.current;
        if (!chart) return;
        chart.setStyles({
            candle: { type: candleType }
        });
    }, [candleType]);

    // Sync active indicators (Main pane overlays + Subpane indicators)
    useEffect(() => {
        const chart = chartInstance.current;
        if (!chart) return;

        // Wipe all existing indicators and extra subpanes cleanly
        try { chart.removeIndicator(); } catch { }

        // 1. Sync Main Pane Overlays (EMA, BOLL, etc directly on candle_pane)
        activeMainIndicators.forEach(name => {
            if (name === "EMA") {
                chart.createIndicator({
                    name: "EMA",
                    paneId: "candle_pane",
                    calcParams: [20, 50, 200],
                    styles: {
                        lines: [
                            { color: CHART_COLORS.ema20, size: 1.5 },
                            { color: CHART_COLORS.ema50, size: 1.5 },
                            { color: CHART_COLORS.ema200, size: 1.5 },
                        ]
                    }
                }, false);
            } else if (name === "BOLL") {
                chart.createIndicator({
                    name: "BOLL",
                    paneId: "candle_pane",
                    calcParams: [20, 2],
                    styles: {
                        lines: [
                            { color: CHART_COLORS.bollUpper, size: 1.5 },
                            { color: CHART_COLORS.bollMid, size: 1.5 },
                            { color: CHART_COLORS.bollLower, size: 1.5 },
                        ]
                    }
                }, false);
            } else {
                chart.createIndicator({ name, paneId: "candle_pane" }, false);
            }
        });

        // 2. Sync Subpane Indicators (VOL, RSI, MACD in dedicated subpanes)
        activeSubIndicators.forEach(name => {
            if (name === "RSI") {
                chart.createIndicator({
                    name: "RSI",
                    paneId: "pane_rsi",
                    calcParams: [14],
                    styles: {
                        lines: [{ color: CHART_COLORS.rsiLine, size: 1.5 }]
                    }
                }, false);
            } else if (name === "MACD") {
                chart.createIndicator({
                    name: "MACD",
                    paneId: "pane_macd",
                    calcParams: [12, 26, 9],
                    styles: {
                        lines: [
                            { color: CHART_COLORS.macdLine, size: 1.5 },
                            { color: CHART_COLORS.macdSignal, size: 1.5 },
                        ]
                    }
                }, false);
            } else if (name === "VOL") {
                chart.createIndicator({
                    name: "VOL",
                    paneId: "pane_vol",
                }, false);
            } else {
                chart.createIndicator({ name, paneId: `pane_${name.toLowerCase()}` }, false);
            }
        });
    }, [activeMainIndicators, activeSubIndicators, candlesLoadedCount]);

    // Reactive Overlays Effect: Re-draw overlays whenever data/ladder/features change
    useEffect(() => {
        const chart = chartInstance.current;
        if (!chart) return;

        chart.removeOverlay();

        const dataList = chart.getDataList();
        // Guard: Do NOT draw overlays before candles are loaded into klinecharts.
        // Creating overlays on an empty chart forces klinecharts to stretch scale domain
        // into the future, squishing candles into a single vertical line.
        if (!dataList || dataList.length < 2) return;

        const activeTrancheA = ladder?.tranche_a_price || entryLevel;
        const activeTrancheB = ladder?.tranche_b_price;
        const activeSL = ladder?.stop_price || slLevel;
        const activeTP1 = ladder?.target_1_price || tpLevel;
        const activeTP2 = ladder?.target_2_price;

        const lastCandle = dataList[dataList.length - 1];
        const lastTs = lastCandle.timestamp;

        const isShort = (activeSL && activeTrancheA && activeSL > activeTrancheA) || tradeDirection === "SHORT";
        const mainTP = (activeTP2 && activeTP2 > 0) ? activeTP2 : (activeTP1 || tpLevel);

        if (activeTrancheA && mainTP && activeSL) {
            let startTs: number;
            let futureTs: number;
            const targetMs = tradeTimestamp ? (tradeTimestamp > 1e11 ? tradeTimestamp : tradeTimestamp * 1000) : 0;

            if (targetMs > 0 && dataList && dataList.length > 0) {
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

        const formatLvlPrice = (v: number) => v < 1 ? v.toFixed(4) : v.toFixed(3);

        // Spatial Level Tag Lines
        if (activeSL && activeSL > 0) {
            chart.createOverlay({
                name: "priceLevelTagLine",
                points: [{ value: activeSL }],
                extendData: {
                    label: `SL · ${formatLvlPrice(activeSL)}`,
                    color: CHART_COLORS.neg,
                    tagBg: "#e11d48"
                }
            });
        }

        if (activeTrancheB && activeTrancheB > 0) {
            chart.createOverlay({
                name: "priceLevelTagLine",
                points: [{ value: activeTrancheB }],
                extendData: {
                    label: `B · ${formatLvlPrice(activeTrancheB)}`,
                    color: "rgba(255, 255, 255, 0.4)",
                    tagBg: "rgba(15, 23, 42, 0.9)" // Slate 900
                }
            });
        }

        if (activeTrancheA && activeTrancheA > 0) {
            chart.createOverlay({
                name: "priceLevelTagLine",
                points: [{ value: activeTrancheA }],
                extendData: {
                    label: `A · ${formatLvlPrice(activeTrancheA)}`,
                    color: "rgba(255, 255, 255, 0.65)",
                    tagBg: "rgba(51, 65, 85, 0.95)" // Slate 700
                }
            });
        }

        if (activeTP1 && activeTP1 > 0) {
            chart.createOverlay({
                name: "priceLevelTagLine",
                points: [{ value: activeTP1 }],
                extendData: {
                    label: `T1 · ${formatLvlPrice(activeTP1)}`,
                    color: CHART_COLORS.pos,
                    tagBg: "#047857"
                }
            });
        }

        if (activeTP2 && activeTP2 > 0) {
            chart.createOverlay({
                name: "priceLevelTagLine",
                points: [{ value: activeTP2 }],
                extendData: {
                    label: `T2 · ${formatLvlPrice(activeTP2)}`,
                    color: "#10b981",
                    tagBg: "#065f46"
                }
            });
        }

        if (showHistory && tradeHistory && tradeHistory.length > 0) {
            tradeHistory.forEach((hist) => {
                const histTs = new Date(hist.computed_at).getTime();
                const histTarget = (hist.target_2_price && hist.target_2_price > 0) ? hist.target_2_price : hist.target_1_price;

                if (!isNaN(histTs) && hist.tranche_a_price && histTarget && hist.stop_price) {
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

        if (features) {
            if (features.swing_high_7d && features.swing_high_7d > 0) {
                chart.createOverlay({
                    name: "horizontalLine",
                    points: [{ value: features.swing_high_7d }],
                    styles: { line: { color: CHART_COLORS.purple, style: "dashed", size: 1 } }
                });
            }
            if (features.swing_shelf_7d && features.swing_shelf_7d > 0) {
                chart.createOverlay({
                    name: "horizontalLine",
                    points: [{ value: features.swing_shelf_7d }],
                    styles: { line: { color: CHART_COLORS.purpleBright, style: "dashed", size: 1 } }
                });
            }
            if (features.vwap_24h && features.vwap_24h > 0) {
                chart.createOverlay({
                    name: "horizontalLine",
                    points: [{ value: features.vwap_24h }],
                    styles: { line: { color: CHART_COLORS.vwapLine, style: "solid", size: 1.5 } }
                });
            }
            if (features.fib_382 && features.fib_382 > 0) {
                chart.createOverlay({
                    name: "horizontalLine",
                    points: [{ value: features.fib_382 }],
                    styles: { line: { color: CHART_COLORS.warn, style: "dashed", size: 1 } }
                });
            }
            if (features.fib_618 && features.fib_618 > 0) {
                chart.createOverlay({
                    name: "horizontalLine",
                    points: [{ value: features.fib_618 }],
                    styles: { line: { color: CHART_COLORS.warn, style: "dashed", size: 1 } }
                });
            }
        }

        // Render GEX Liquidity Zones Overlays (Intensity-Based Bands)
        if (showGexZones && gexData) {
            const callWall = gexData.call_wall;
            const putWall = gexData.put_wall;
            const flip = gexData.gamma_flip;

            const callWallItem = (gexData.formatted_walls || []).find((w: any) => w.strike === callWall) ||
                (gexData.gex_curve || []).find((c: any) => c.strike === callWall);
            const putWallItem = (gexData.formatted_walls || []).find((w: any) => w.strike === putWall) ||
                (gexData.gex_curve || []).find((c: any) => c.strike === putWall);

            const callGexM = Math.abs(callWallItem?.gex_impact || callWallItem?.call_gex || callWallItem?.net_gex || 3.0);
            const putGexM = Math.abs(putWallItem?.gex_impact || putWallItem?.put_gex || putWallItem?.net_gex || 3.0);

            // Dynamic band height based on GEX intensity (10px min to 28px max)
            const callHeight = Math.min(28, Math.max(10, Math.round(callGexM * 2.5 + 8)));
            const putHeight = Math.min(28, Math.max(10, Math.round(putGexM * 2.5 + 8)));

            const formatGexStr = (m: number) => m >= 1 ? `${m.toFixed(1)}M` : `${(m * 1000).toFixed(0)}K`;

            if (callWall && callWall > 0) {
                chart.createOverlay({
                    name: "gexLiquidityZone",
                    points: [{ value: callWall }],
                    extendData: {
                        label: `Call Wall · ${formatLvlPrice(callWall)} (+$${formatGexStr(callGexM)})`,
                        fillColor: "rgba(244, 63, 94, 0.22)",
                        borderColor: "#f43f5e",
                        tagBg: "rgba(225, 29, 72, 0.95)",
                        height: callHeight,
                        isDashed: false
                    }
                });
            }

            if (putWall && putWall > 0) {
                chart.createOverlay({
                    name: "gexLiquidityZone",
                    points: [{ value: putWall }],
                    extendData: {
                        label: `Put Wall · ${formatLvlPrice(putWall)} (-$${formatGexStr(putGexM)})`,
                        fillColor: "rgba(16, 185, 129, 0.22)",
                        borderColor: "#10b981",
                        tagBg: "rgba(4, 120, 87, 0.95)",
                        height: putHeight,
                        isDashed: false
                    }
                });
            }

            if (flip && flip > 0 && flip !== callWall && flip !== putWall) {
                chart.createOverlay({
                    name: "gexLiquidityZone",
                    points: [{ value: flip }],
                    extendData: {
                        label: `Gamma Flip · ${formatLvlPrice(flip)}`,
                        fillColor: "rgba(234, 179, 8, 0.10)",
                        borderColor: "#eab308",
                        tagBg: "rgba(161, 98, 7, 0.95)",
                        height: 4,
                        isDashed: true
                    }
                });
            }
        }
    }, [productId, entryLevel, tpLevel, slLevel, tradeTimestamp, features, ladder, tradeHistory, tradeDirection, showHistory, showGexZones, gexData, granularity, candlesLoadedCount]);

    // Live Data WebSocket (Candles)
    useEffect(() => {
        const wsUrl = `${wsBase()}/api/v1/ws/candles/${productId}`;

        let ws: WebSocket;
        let disposed = false;
        let liveDisabled = false;
        let interval: any;

        const connect = () => {
            ws = new WebSocket(wsUrl);

            ws.onopen = () => {
                if (disposed) { ws.close(); return; }
                setIsLive(true);
                interval = setInterval(() => ws.readyState === WebSocket.OPEN && ws.send("ping"), 20000);
            };

            ws.onmessage = (e) => {
                if (disposed) return;
                try {
                    const tick = JSON.parse(e.data);
                    if (tick && (tick.type === "ws_disabled" || tick.error === "live_ws_disabled" || tick.type === "ping_tick")) {
                        if (tick.type === "ws_disabled" || tick.error === "live_ws_disabled") {
                            liveDisabled = true;
                            setIsLive(false);
                        }
                        return;
                    }

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
                if (liveDisabled) return;
                if (!disposed) setTimeout(connect, 3000);
            };
        };

        connect();
        return () => {
            disposed = true;
            setIsLive(false);
            clearInterval(interval);
            if (ws && ws.readyState === WebSocket.OPEN) ws.close();
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

    const toggleMainIndicator = (name: string) => {
        setActiveMainIndicators(prev =>
            prev.includes(name) ? prev.filter(i => i !== name) : [...prev, name]
        );
    };

    const toggleSubIndicator = (name: string) => {
        setActiveSubIndicators(prev =>
            prev.includes(name) ? prev.filter(i => i !== name) : [...prev, name]
        );
    };

    const applyPreset = (preset: typeof STRATEGY_PRESETS[0]) => {
        setActiveMainIndicators(preset.main);
        setActiveSubIndicators(preset.sub);
        setShowPresetMenu(false);
    };

    const resetZoom = () => {
        if (!chartInstance.current) return;
        const dataList = chartInstance.current.getDataList();
        if (dataList && dataList.length > 0) {
            chartInstance.current.scrollToTimestamp(dataList[dataList.length - 1].timestamp);
        }
    };

    const toggleFullscreen = () => {
        if (!chartWrapperRef.current) return;
        if (!isFullscreen) {
            if (chartWrapperRef.current.requestFullscreen) {
                chartWrapperRef.current.requestFullscreen();
            }
        } else {
            if (document.exitFullscreen) {
                document.exitFullscreen();
            }
        }
        setIsFullscreen(!isFullscreen);
    };

    return (
        <div
            ref={chartWrapperRef}
            style={{
                position: isFullscreen ? "fixed" : "relative",
                top: isFullscreen ? 0 : undefined,
                left: isFullscreen ? 0 : undefined,
                width: "100%",
                height: isFullscreen ? "100vh" : undefined,
                zIndex: isFullscreen ? 9999 : undefined,
                background: "var(--surface-0)",
                display: "flex",
                flexDirection: "column",
                gap: "0.4rem",
                padding: isFullscreen ? "0.75rem" : 0
            }}
        >
            {/* Top Control Bar Header */}
            <div style={{
                display: "flex",
                flexWrap: "wrap",
                alignItems: "center",
                justifyContent: "space-between",
                background: "var(--surface-2)",
                padding: "0.5rem 0.75rem",
                borderRadius: 0,
                border: "1px solid rgba(255,255,255,0.06)",
                gap: "0.5rem"
            }}>
                {/* Left controls: Timeframes & Candle Styles */}
                <div style={{ display: "flex", gap: "0.4rem", alignItems: "center" }}>
                    {/* Timeframes */}
                    {[
                        { label: "15M", val: 900 },
                        { label: "1H", val: 3600 },
                        { label: "4H", val: 14400 },
                        { label: "1D", val: 86400 },
                    ].map((tf) => (
                        <button
                            key={tf.val}
                            onClick={() => setGranularity(tf.val)}
                            style={{
                                background: granularity === tf.val ? "rgba(6, 182, 212, 0.2)" : "rgba(255,255,255,0.04)",
                                border: granularity === tf.val ? "1px solid rgba(6, 182, 212, 0.5)" : "1px solid rgba(255,255,255,0.08)",
                                color: granularity === tf.val ? "var(--info)" : "var(--text-muted)",
                                padding: "0.3rem 0.55rem",
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

                    <div style={{ width: "1px", height: "16px", background: "rgba(255,255,255,0.1)", margin: "0 0.2rem" }} />

                    {/* Chart Style Switcher */}
                    {[
                        { type: "candle_solid", label: "🕯️ Candle" },
                        { type: "ohlc", label: "📊 OHLC" },
                        { type: "area", label: "📈 Line" },
                    ].map(st => (
                        <button
                            key={st.type}
                            onClick={() => setCandleType(st.type as any)}
                            style={{
                                background: candleType === st.type ? "rgba(168, 85, 247, 0.2)" : "transparent",
                                border: candleType === st.type ? "1px solid rgba(168, 85, 247, 0.5)" : "1px solid transparent",
                                color: candleType === st.type ? "var(--purpleBright)" : "var(--text-4)",
                                padding: "0.3rem 0.5rem",
                                borderRadius: 0,
                                fontSize: "0.65rem",
                                fontWeight: 700,
                                cursor: "pointer",
                                fontFamily: "var(--font-jetbrains)",
                            }}
                        >
                            {st.label}
                        </button>
                    ))}
                </div>

                {/* Center / Right controls: Presets, Indicators Modal, History & Heatmap Toggles */}
                <div style={{ display: "flex", gap: "0.4rem", alignItems: "center", position: "relative" }}>
                    {/* Strategy Presets Dropdown */}
                    <div style={{ position: "relative" }}>
                        <button
                            onClick={() => { setShowPresetMenu(!showPresetMenu); setShowIndicatorMenu(false); }}
                            style={{
                                background: "rgba(59, 130, 246, 0.15)",
                                border: "1px solid rgba(59, 130, 246, 0.4)",
                                color: "var(--blueBright)",
                                padding: "0.3rem 0.65rem",
                                fontSize: "0.65rem",
                                fontWeight: 800,
                                cursor: "pointer",
                                display: "flex",
                                alignItems: "center",
                                gap: "0.3rem",
                                fontFamily: "var(--font-jetbrains)",
                            }}
                        >
                            <Zap size={11} />
                            <span>Presets</span>
                            <ChevronDown size={11} />
                        </button>
                        {showPresetMenu && (
                            <div style={{
                                position: "absolute", top: "100%", right: 0, marginTop: "0.3rem", zIndex: 100,
                                background: "var(--surface-1)", border: "1px solid rgba(255,255,255,0.12)",
                                padding: "0.5rem", display: "flex", flexDirection: "column", gap: "0.3rem",
                                width: "160px", boxShadow: "0 10px 25px rgba(0,0,0,0.6)"
                            }}>
                                {STRATEGY_PRESETS.map(p => (
                                    <button
                                        key={p.id}
                                        onClick={() => applyPreset(p)}
                                        style={{
                                            background: "rgba(255,255,255,0.03)",
                                            border: "none",
                                            color: "var(--text-1)",
                                            padding: "0.4rem 0.5rem",
                                            fontSize: "0.7rem",
                                            fontWeight: 700,
                                            textAlign: "left",
                                            cursor: "pointer",
                                            display: "flex",
                                            justifyContent: "space-between",
                                            alignItems: "center"
                                        }}
                                    >
                                        <span>{p.name}</span>
                                    </button>
                                ))}
                            </div>
                        )}
                    </div>

                    {/* Technical Indicators Dropdown */}
                    <div style={{ position: "relative" }}>
                        <button
                            onClick={() => { setShowIndicatorMenu(!showIndicatorMenu); setShowPresetMenu(false); }}
                            style={{
                                background: (activeMainIndicators.length > 0 || activeSubIndicators.length > 0) ? "rgba(6, 182, 212, 0.2)" : "rgba(255,255,255,0.04)",
                                border: "1px solid rgba(6, 182, 212, 0.5)",
                                color: "var(--info)",
                                padding: "0.3rem 0.65rem",
                                fontSize: "0.65rem",
                                fontWeight: 800,
                                cursor: "pointer",
                                display: "flex",
                                alignItems: "center",
                                gap: "0.35rem",
                                fontFamily: "var(--font-jetbrains)",
                            }}
                        >
                            <Sliders size={11} />
                            <span>Indicators ({activeMainIndicators.length + activeSubIndicators.length})</span>
                            <ChevronDown size={11} />
                        </button>

                        {showIndicatorMenu && (
                            <div style={{
                                position: "absolute", top: "100%", right: 0, marginTop: "0.3rem", zIndex: 100,
                                background: "var(--surface-1)", border: "1px solid rgba(255,255,255,0.12)",
                                padding: "0.6rem", display: "flex", flexDirection: "column", gap: "0.6rem",
                                width: "230px", boxShadow: "0 10px 25px rgba(0,0,0,0.6)"
                            }}>
                                <div>
                                    <div style={{ fontSize: "0.6rem", fontWeight: 800, color: "var(--text-4)", textTransform: "uppercase", marginBottom: "0.3rem", letterSpacing: "0.05em" }}>
                                        Overlays (Main Pane)
                                    </div>
                                    <div style={{ display: "flex", flexDirection: "column", gap: "0.25rem" }}>
                                        {MAIN_INDICATOR_OPTIONS.map(opt => {
                                            const isActive = activeMainIndicators.includes(opt.name);
                                            return (
                                                <button
                                                    key={opt.name}
                                                    onClick={() => toggleMainIndicator(opt.name)}
                                                    style={{
                                                        background: isActive ? "rgba(6, 182, 212, 0.15)" : "rgba(255,255,255,0.02)",
                                                        border: "none",
                                                        color: isActive ? "var(--info)" : "var(--text-3)",
                                                        padding: "0.3rem 0.5rem",
                                                        fontSize: "0.68rem",
                                                        fontWeight: 700,
                                                        textAlign: "left",
                                                        cursor: "pointer",
                                                        display: "flex",
                                                        alignItems: "center",
                                                        justifyContent: "space-between"
                                                    }}
                                                >
                                                    <span style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                                                        <span style={{ width: "8px", height: "8px", borderRadius: "50%", background: opt.color }} />
                                                        {opt.label}
                                                    </span>
                                                    {isActive && <Check size={11} color="var(--info)" />}
                                                </button>
                                            );
                                        })}
                                    </div>
                                </div>

                                <div style={{ borderTop: "1px solid rgba(255,255,255,0.06)", paddingTop: "0.4rem" }}>
                                    <div style={{ fontSize: "0.6rem", fontWeight: 800, color: "var(--text-4)", textTransform: "uppercase", marginBottom: "0.3rem", letterSpacing: "0.05em" }}>
                                        Subpanes (Oscillators)
                                    </div>
                                    <div style={{ display: "flex", flexDirection: "column", gap: "0.25rem" }}>
                                        {SUB_INDICATOR_OPTIONS.map(opt => {
                                            const isActive = activeSubIndicators.includes(opt.name);
                                            return (
                                                <button
                                                    key={opt.name}
                                                    onClick={() => toggleSubIndicator(opt.name)}
                                                    style={{
                                                        background: isActive ? "rgba(16, 185, 129, 0.15)" : "rgba(255,255,255,0.02)",
                                                        border: "none",
                                                        color: isActive ? "var(--pos)" : "var(--text-3)",
                                                        padding: "0.3rem 0.5rem",
                                                        fontSize: "0.68rem",
                                                        fontWeight: 700,
                                                        textAlign: "left",
                                                        cursor: "pointer",
                                                        display: "flex",
                                                        alignItems: "center",
                                                        justifyContent: "space-between"
                                                    }}
                                                >
                                                    <span style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                                                        <span style={{ width: "8px", height: "8px", borderRadius: "50%", background: opt.color }} />
                                                        {opt.label}
                                                    </span>
                                                    {isActive && <Check size={11} color="var(--pos)" />}
                                                </button>
                                            );
                                        })}
                                    </div>
                                </div>
                            </div>
                        )}
                    </div>

                    {/* GEX Liquidity Zones Toggle */}
                    <button
                        onClick={() => setShowGexZones(!showGexZones)}
                        title="Toggle GEX-Based Liquidity Zones (Call/Put Walls & Gamma Flip)"
                        style={{
                            background: showGexZones ? "rgba(6, 182, 212, 0.2)" : "rgba(255,255,255,0.04)",
                            border: showGexZones ? "1px solid rgba(6, 182, 212, 0.5)" : "1px solid rgba(255,255,255,0.08)",
                            color: showGexZones ? "var(--info)" : "var(--text-muted)",
                            padding: "0.3rem 0.55rem",
                            fontSize: "0.65rem",
                            fontWeight: 800,
                            cursor: "pointer",
                            fontFamily: "var(--font-jetbrains)",
                        }}
                    >
                        ⚡ {showGexZones ? "GEX ZONES ON" : "GEX ZONES OFF"}
                    </button>

                    {/* Heatmap Toggle */}
                    <button
                        onClick={() => setShowHeatmap(!showHeatmap)}
                        title="Toggle Orderbook Depth Heatmap Bars"
                        style={{
                            background: showHeatmap ? "rgba(168, 85, 247, 0.2)" : "rgba(255,255,255,0.04)",
                            border: showHeatmap ? "1px solid rgba(168, 85, 247, 0.5)" : "1px solid rgba(255,255,255,0.08)",
                            color: showHeatmap ? "var(--purpleBright)" : "var(--text-muted)",
                            padding: "0.3rem 0.55rem",
                            fontSize: "0.65rem",
                            fontWeight: 800,
                            cursor: "pointer",
                            fontFamily: "var(--font-jetbrains)",
                        }}
                    >
                        🧱 {showHeatmap ? "HEATMAP ON" : "HEATMAP OFF"}
                    </button>

                    {/* History Toggle */}
                    <button
                        onClick={() => setShowHistory(!showHistory)}
                        title="Toggle Historical Setup Boxes"
                        style={{
                            background: showHistory ? "rgba(16, 185, 129, 0.2)" : "rgba(255,255,255,0.04)",
                            border: showHistory ? "1px solid rgba(16, 185, 129, 0.5)" : "1px solid rgba(255,255,255,0.08)",
                            color: showHistory ? "var(--pos)" : "var(--text-muted)",
                            padding: "0.3rem 0.55rem",
                            fontSize: "0.65rem",
                            fontWeight: 800,
                            cursor: "pointer",
                            fontFamily: "var(--font-jetbrains)",
                        }}
                    >
                        📜 {showHistory ? "HIST ON" : "HIST OFF"}
                    </button>

                    {/* Reset Zoom */}
                    <button
                        onClick={resetZoom}
                        title="Reset Zoom to Latest Price Action"
                        style={{
                            background: "rgba(255,255,255,0.04)",
                            border: "1px solid rgba(255,255,255,0.08)",
                            color: "var(--text-3)",
                            padding: "0.3rem 0.45rem",
                            cursor: "pointer",
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "center"
                        }}
                    >
                        <RotateCcw size={12} />
                    </button>

                    {/* Fullscreen Toggle */}
                    <button
                        onClick={toggleFullscreen}
                        title="Toggle Chart Fullscreen"
                        style={{
                            background: "rgba(255,255,255,0.04)",
                            border: "1px solid rgba(255,255,255,0.08)",
                            color: "var(--text-3)",
                            padding: "0.3rem 0.45rem",
                            cursor: "pointer",
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "center"
                        }}
                    >
                        {isFullscreen ? <Minimize2 size={12} /> : <Maximize2 size={12} />}
                    </button>

                    {/* Live Indicator Dot */}
                    <div style={{ display: "flex", alignItems: "center", gap: "0.35rem", marginLeft: "0.3rem" }}>
                        <span style={{
                            width: "7px", height: "7px", borderRadius: "50%",
                            background: isLive ? "var(--pos)" : "var(--text-4)",
                            boxShadow: isLive ? "0 0 6px var(--pos)" : "none",
                            display: "inline-block",
                        }} />
                        <span style={{ fontSize: "0.6rem", fontWeight: 800, color: isLive ? "var(--pos)" : "var(--text-4)", textTransform: "uppercase", fontFamily: "var(--font-jetbrains)" }}>
                            {isLive ? "LIVE" : "OFFLINE"}
                        </span>
                    </div>
                </div>
            </div>

            {/* Active Indicator Pills Toolbar */}
            {(activeMainIndicators.length > 0 || activeSubIndicators.length > 0) && (
                <div style={{ display: "flex", flexWrap: "wrap", gap: "0.3rem", alignItems: "center", padding: "0.2rem 0.5rem" }}>
                    <span style={{ fontSize: "0.6rem", fontWeight: 800, color: "var(--text-dim)", textTransform: "uppercase" }}>ACTIVE:</span>
                    {activeMainIndicators.map(ind => (
                        <span
                            key={ind}
                            style={{
                                display: "inline-flex", alignItems: "center", gap: "0.25rem",
                                background: "rgba(6, 182, 212, 0.12)", border: "1px solid rgba(6, 182, 212, 0.3)",
                                color: "var(--info)", padding: "0.1rem 0.35rem", fontSize: "0.6rem", fontWeight: 700
                            }}
                        >
                            {ind}
                            <button
                                onClick={() => toggleMainIndicator(ind)}
                                style={{ background: "transparent", border: "none", color: "var(--info)", cursor: "pointer", fontSize: "0.6rem", padding: 0 }}
                            >
                                ×
                            </button>
                        </span>
                    ))}
                    {activeSubIndicators.map(ind => (
                        <span
                            key={ind}
                            style={{
                                display: "inline-flex", alignItems: "center", gap: "0.25rem",
                                background: "rgba(16, 185, 129, 0.12)", border: "1px solid rgba(16, 185, 129, 0.3)",
                                color: "var(--pos)", padding: "0.1rem 0.35rem", fontSize: "0.6rem", fontWeight: 700
                            }}
                        >
                            {ind}
                            <button
                                onClick={() => toggleSubIndicator(ind)}
                                style={{ background: "transparent", border: "none", color: "var(--pos)", cursor: "pointer", fontSize: "0.6rem", padding: 0 }}
                            >
                                ×
                            </button>
                        </span>
                    ))}
                </div>
            )}

            {/* Chart Canvas Container */}
            <div
                style={{
                    width: "100%",
                    height: isFullscreen ? "calc(100vh - 80px)" : (typeof height === "number" ? `${height}px` : height),
                    minHeight: "400px",
                    background: "var(--surface-3)",
                    border: "none",
                    borderRadius: 0,
                    overflow: "hidden",
                    position: "relative",
                    resize: isFullscreen ? "none" : "vertical",
                }}
            >
                {/* Drawing Toolbar Overlay */}
                <div style={{
                    position: "absolute", top: "1rem", left: "1rem", zIndex: 20,
                    display: "flex", flexDirection: "column", gap: "0.4rem",
                    background: "linear-gradient(145deg, rgba(30, 41, 59, 0.7) 0%, rgba(15, 23, 42, 0.8) 100%)",
                    backdropFilter: "blur(16px)",
                    WebkitBackdropFilter: "blur(16px)", // for Safari support
                    padding: "0.6rem", borderRadius: "9999px",
                    border: "1px solid rgba(255,255,255,0.15)",
                    boxShadow: "0 8px 32px rgba(0,0,0,0.5), inset 0 1px 0 rgba(255,255,255,0.1)"
                }}>
                    {[
                        { id: "segment", icon: <Pencil size={18} />, label: "Trend Line" },
                        { id: "rayLine", icon: <ArrowRight size={18} />, label: "Ray Line" },
                        { id: "horizontalLine", icon: <Minus size={18} />, label: "Horiz Line" },
                        { id: "fibonacciLine", icon: <MousePointer2 size={18} />, label: "Fibonacci" }
                    ].map(tool => (
                        <button
                            key={tool.id}
                            title={tool.label}
                            onClick={() => activateDrawingTool(tool.id)}
                            style={{
                                width: "42px", height: "42px",
                                display: "flex", alignItems: "center", justifyContent: "center",
                                background: currentTool === tool.id ? "rgba(6, 182, 212, 0.2)" : "transparent",
                                color: currentTool === tool.id ? "var(--info)" : "var(--text-3)",
                                border: currentTool === tool.id ? "1px solid rgba(6, 182, 212, 0.5)" : "1px solid transparent",
                                cursor: "pointer", borderRadius: "50%",
                                transition: "all 0.3s cubic-bezier(0.4, 0, 0.2, 1)",
                                boxShadow: currentTool === tool.id ? "0 0 12px rgba(6, 182, 212, 0.3)" : "none"
                            }}
                            onMouseOver={(e) => {
                                if (currentTool !== tool.id) {
                                    e.currentTarget.style.color = "var(--text-1)";
                                    e.currentTarget.style.background = "rgba(255,255,255,0.1)";
                                    e.currentTarget.style.transform = "scale(1.05)";
                                }
                            }}
                            onMouseOut={(e) => {
                                if (currentTool !== tool.id) {
                                    e.currentTarget.style.color = "var(--text-3)";
                                    e.currentTarget.style.background = "transparent";
                                    e.currentTarget.style.transform = "scale(1)";
                                }
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
                    <div style={{ fontSize: "1.5rem", fontWeight: 800, color: "rgba(255,255,255,0.08)", fontFamily: "var(--font-jetbrains)" }}>
                        {productId}
                    </div>
                </div>
            </div>
        </div>
    );
};

export default NativeChart;
