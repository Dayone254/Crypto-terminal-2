"use client";

import React, { useEffect, useRef } from "react";

interface TradingViewChartProps {
    productId: string;
    interval?: string;
    height?: string | number;
}

export const TradingViewChart: React.FC<TradingViewChartProps> = ({
    productId,
    interval = "60",
    height = "650px",
}) => {
    const containerRef = useRef<HTMLDivElement>(null);

    const formattedSymbol = `COINBASE:${productId.replace("-", "")}`;

    useEffect(() => {
        if (!containerRef.current) return;

        containerRef.current.innerHTML = "";

        const script = document.createElement("script");
        script.src = "https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js";
        script.type = "text/javascript";
        script.async = true;
        script.innerHTML = JSON.stringify({
            autosize: true,
            symbol: formattedSymbol,
            interval: interval,
            timezone: "Africa/Nairobi",
            theme: "dark",
            style: "1",
            locale: "en",
            enable_publishing: false,
            allow_symbol_change: true,
            calendar: false,
            support_host: "https://www.tradingview.com",
            backgroundColor: "#080A0F",
            gridColor: "rgba(255, 255, 255, 0.04)",
            hide_side_toolbar: false,
            details: true,
            hotlist: false,
        });

        const widgetContainer = document.createElement("div");
        widgetContainer.className = "tradingview-widget-container__widget";
        widgetContainer.style.height = "100%";
        widgetContainer.style.width = "100%";

        containerRef.current.appendChild(widgetContainer);
        containerRef.current.appendChild(script);
    }, [formattedSymbol, interval]);

    return (
        <div
            style={{
                width: "100%",
                height: typeof height === "number" ? `${height}px` : height,
                background: "#080A0F",
                border: "none",
                borderRadius: 0,
                overflow: "hidden",
                position: "relative",
            }}
        >
            <div
                ref={containerRef}
                className="tradingview-widget-container"
                style={{ height: "100%", width: "100%" }}
            />
        </div>
    );
};
