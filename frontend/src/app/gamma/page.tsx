"use client";

import React, { useState } from "react";
import { Sidebar } from "@/components/Sidebar";
import { Header } from "@/components/Header";
import { Footer } from "@/components/Footer";
import { GammaEngineVisualizer } from "@/components/GammaEngineVisualizer";

export default function GammaPage() {
    const [selectedSymbol, setSelectedSymbol] = useState<string>("BTC-USD");

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
                <div style={{ padding: "1rem 1.25rem" }}>
                    <GammaEngineVisualizer
                        symbol={selectedSymbol}
                        onSelectSymbol={(sym) => setSelectedSymbol(sym)}
                    />
                </div>
            </main>

            <Footer />
        </div>
    );
}
