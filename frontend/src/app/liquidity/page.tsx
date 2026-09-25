"use client";

import React from "react";
import { Sidebar } from "@/components/Sidebar";
import { Header } from "@/components/Header";
import { Footer } from "@/components/Footer";
import { LiquidityHeatmapVisualizer } from "@/components/LiquidityHeatmapVisualizer";

export default function LiquidityPage() {
    return (
        <div style={{ minHeight: "100vh", backgroundColor: "var(--surface-container-lowest)", color: "var(--on-surface)" }}>
            <Sidebar />
            <Header />

            <main
                style={{
                    paddingLeft: "var(--sidebar-width, 256px)",
                    paddingTop: "112px",
                    paddingBottom: "32px",
                    minHeight: "100vh",
                }}
            >
                <LiquidityHeatmapVisualizer />
            </main>

            <Footer />
        </div>
    );
}
