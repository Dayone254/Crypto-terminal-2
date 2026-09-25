"use client";

import React from "react";
import { Sidebar } from "@/components/Sidebar";
import { Header } from "@/components/Header";
import { Footer } from "@/components/Footer";
import { AltcoinRSRadar } from "@/components/AltcoinRSRadar";
import { useRouter } from "next/navigation";

export default function RadarPage() {
    const router = useRouter();

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
                    <AltcoinRSRadar
                        onSelectSymbol={(sym) => router.push(`/market/${encodeURIComponent(sym)}`)}
                    />
                </div>
            </main>

            <Footer />
        </div>
    );
}
