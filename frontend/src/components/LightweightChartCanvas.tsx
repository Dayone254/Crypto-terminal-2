"use client";

import React, { useEffect, useRef } from "react";
import {
    createChart,
    IChartApi,
    ISeriesApi,
    CandlestickSeries,
    HistogramSeries,
    CandlestickData,
    Time,
    ColorType,
    LineStyle
} from "lightweight-charts";

export interface LadderData {
    entryPrice: number;
    stopLoss: number;
    tp1: number;
    tp2?: number;
    tp3?: number;
    bias: "LONG" | "SHORT";
    score: number;
}

interface LightweightChartCanvasProps {
    productId: string;
    candles: Array<{
        timestamp: number;
        open: number;
        high: number;
        low: number;
        close: number;
        volume: number;
    }>;
    ladder?: LadderData | null;
    height?: number | string;
}

export const LightweightChartCanvas: React.FC<LightweightChartCanvasProps> = ({
    productId,
    candles,
    ladder,
    height = 550,
}) => {
    const chartContainerRef = useRef<HTMLDivElement>(null);
    const chartRef = useRef<IChartApi | null>(null);
    const candleSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
    const volumeSeriesRef = useRef<ISeriesApi<"Histogram"> | null>(null);

    useEffect(() => {
        if (!chartContainerRef.current) return;

        // Initialize 60 FPS Lightweight Chart Canvas
        const chart = createChart(chartContainerRef.current, {
            width: chartContainerRef.current.clientWidth,
            height: typeof height === "number" ? height : 550,
            layout: {
                background: { type: ColorType.Solid, color: "#0B0E14" },
                textColor: "#94A3B8",
                fontSize: 12,
            },
            grid: {
                vertLines: { color: "rgba(255, 255, 255, 0.04)", style: LineStyle.Solid },
                horzLines: { color: "rgba(255, 255, 255, 0.04)", style: LineStyle.Solid },
            },
            rightPriceScale: {
                borderColor: "rgba(255, 255, 255, 0.08)",
                autoScale: true,
            },
            timeScale: {
                borderColor: "rgba(255, 255, 255, 0.08)",
                timeVisible: true,
                secondsVisible: false,
            },
            crosshair: {
                vertLine: { color: "#38BDF8", width: 1, style: LineStyle.Dashed },
                horzLine: { color: "#38BDF8", width: 1, style: LineStyle.Dashed },
            },
        });

        chartRef.current = chart;

        // Add Candlestick Series using lightweight-charts v5 API
        const candleSeries = chart.addSeries(CandlestickSeries, {
            upColor: "#10B981",
            downColor: "#EF4444",
            borderUpColor: "#10B981",
            borderDownColor: "#EF4444",
            wickUpColor: "#10B981",
            wickDownColor: "#EF4444",
        });
        candleSeriesRef.current = candleSeries;

        // Add Volume Histogram Series using lightweight-charts v5 API
        const volumeSeries = chart.addSeries(HistogramSeries, {
            color: "#3B82F6",
            priceFormat: { type: "volume" },
            priceScaleId: "volume",
        });
        volumeSeriesRef.current = volumeSeries;

        chart.priceScale("volume").applyOptions({
            scaleMargins: { top: 0.8, bottom: 0 },
        });

        const handleResize = () => {
            if (chartContainerRef.current && chartRef.current) {
                chartRef.current.applyOptions({
                    width: chartContainerRef.current.clientWidth,
                });
            }
        };

        window.addEventListener("resize", handleResize);

        return () => {
            window.removeEventListener("resize", handleResize);
            chart.remove();
        };
    }, [height]);

    // Update Candles Data
    useEffect(() => {
        if (!candleSeriesRef.current || !volumeSeriesRef.current || !candles.length) return;

        const formattedCandles: CandlestickData<Time>[] = candles.map((c) => ({
            time: (c.timestamp / 1000) as Time,
            open: c.open,
            high: c.high,
            low: c.low,
            close: c.close,
        }));

        const formattedVolume = candles.map((c) => ({
            time: (c.timestamp / 1000) as Time,
            value: c.volume,
            color: c.close >= c.open ? "rgba(16, 185, 129, 0.4)" : "rgba(239, 68, 68, 0.4)",
        }));

        candleSeriesRef.current.setData(formattedCandles);
        volumeSeriesRef.current.setData(formattedVolume);
    }, [candles]);

    // Render Setup Limit Ladder (Entry, Stop Loss, TP1-3)
    useEffect(() => {
        if (!candleSeriesRef.current) return;

        // Clear previous price lines if any
        // (Price lines in lightweight-charts are attached to series)
        if (ladder) {
            // Entry Line
            candleSeriesRef.current.createPriceLine({
                price: ladder.entryPrice,
                color: "#38BDF8",
                lineWidth: 2,
                lineStyle: LineStyle.Solid,
                axisLabelVisible: true,
                title: `ENTRY (${ladder.bias})`,
            });

            // Stop Loss Line
            candleSeriesRef.current.createPriceLine({
                price: ladder.stopLoss,
                color: "#EF4444",
                lineWidth: 2,
                lineStyle: LineStyle.Dashed,
                axisLabelVisible: true,
                title: "STOP LOSS",
            });

            // Take Profit 1 Line
            candleSeriesRef.current.createPriceLine({
                price: ladder.tp1,
                color: "#10B981",
                lineWidth: 2,
                lineStyle: LineStyle.Dashed,
                axisLabelVisible: true,
                title: "TP1",
            });

            if (ladder.tp2) {
                candleSeriesRef.current.createPriceLine({
                    price: ladder.tp2,
                    color: "#059669",
                    lineWidth: 1,
                    lineStyle: LineStyle.Dotted,
                    axisLabelVisible: true,
                    title: "TP2",
                });
            }
        }
    }, [ladder]);

    return (
        <div className="relative w-full h-full bg-[#0B0E14] overflow-hidden rounded-lg border border-slate-800">
            <div className="absolute top-3 left-3 z-10 flex items-center space-x-2 bg-slate-900/80 backdrop-blur-md px-3 py-1.5 rounded-md border border-slate-800 text-xs font-mono text-slate-300">
                <span className="font-bold text-sky-400">{productId}</span>
                <span className="text-slate-500">|</span>
                <span>TradingView Lightweight Canvas v5</span>
                {ladder && (
                    <>
                        <span className="text-slate-500">|</span>
                        <span className={ladder.bias === "LONG" ? "text-emerald-400 font-bold" : "text-rose-400 font-bold"}>
                            {ladder.bias} ({ladder.score.toFixed(1)} PTS)
                        </span>
                    </>
                )}
            </div>
            <div ref={chartContainerRef} className="w-full h-full" />
        </div>
    );
};
