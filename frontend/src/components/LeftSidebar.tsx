"use client";

import React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { LayoutGrid, Radio, Activity, BarChart2, Sliders, Bookmark, Settings, Zap } from "lucide-react";

export const LeftSidebar: React.FC = () => {
    const pathname = usePathname();

    const navItems = [
        { name: "Scanner", icon: LayoutGrid, href: "/" },
        { name: "Radar", icon: Radio, href: "/#radar" },
        { name: "Gamma", icon: Activity, href: "/gamma" },
        { name: "Flow", icon: BarChart2, href: "/#flow" },
        { name: "Research", icon: Sliders, href: "/research" },
    ];

    return (
        <aside style={{
            width: "220px",
            background: "#070A10",
            borderRight: "1px solid rgba(255, 255, 255, 0.07)",
            display: "flex",
            flexDirection: "column",
            justifyContent: "space-between",
            padding: "1.25rem 0.85rem",
            userSelect: "none"
        }}>
            {/* Top Section: Brand & Nav Links */}
            <div style={{ display: "flex", flexDirection: "column", gap: "1.75rem" }}>
                {/* Brand Logo */}
                <div style={{ display: "flex", alignItems: "center", gap: "0.6rem", paddingLeft: "0.5rem" }}>
                    <div style={{
                        width: "30px",
                        height: "30px",
                        borderRadius: "6px",
                        background: "rgba(6, 182, 212, 0.15)",
                        border: "1px solid rgba(6, 182, 212, 0.3)",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center"
                    }}>
                        <Zap size={18} color="#06b6d4" fill="#06b6d4" />
                    </div>
                    <span style={{
                        fontSize: "0.95rem",
                        fontWeight: 900,
                        color: "#f8fafc",
                        letterSpacing: "-0.02em"
                    }}>
                        TAPERADAR X1
                    </span>
                </div>

                {/* Main Navigation Links */}
                <nav style={{ display: "flex", flexDirection: "column", gap: "0.35rem" }}>
                    {navItems.map((item) => {
                        const Icon = item.icon;
                        const isActive = pathname === item.href || (item.name === "Gamma" && pathname === "/gamma");
                        return (
                            <Link
                                key={item.name}
                                href={item.href}
                                style={{
                                    display: "flex",
                                    alignItems: "center",
                                    gap: "0.75rem",
                                    padding: "0.65rem 0.85rem",
                                    borderRadius: "8px",
                                    fontSize: "0.8rem",
                                    fontWeight: isActive ? 800 : 600,
                                    color: isActive ? "#ffffff" : "#94a3b8",
                                    background: isActive
                                        ? "linear-gradient(90deg, rgba(6, 182, 212, 0.2) 0%, rgba(6, 182, 212, 0.05) 100%)"
                                        : "transparent",
                                    borderLeft: isActive ? "3px solid #06b6d4" : "3px solid transparent",
                                    textDecoration: "none",
                                    transition: "all 0.15s ease"
                                }}
                            >
                                <Icon size={17} color={isActive ? "#06b6d4" : "#64748b"} />
                                <span>{item.name}</span>
                            </Link>
                        );
                    })}
                </nav>
            </div>

            {/* Bottom Section: Watchlist, Settings, & Version Footer */}
            <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                <Link
                    href="/#watchlist"
                    style={{
                        display: "flex",
                        alignItems: "center",
                        gap: "0.75rem",
                        padding: "0.6rem 0.85rem",
                        borderRadius: "8px",
                        fontSize: "0.78rem",
                        fontWeight: 600,
                        color: "#94a3b8",
                        textDecoration: "none"
                    }}
                >
                    <Bookmark size={16} color="#64748b" />
                    <span>Watchlist</span>
                </Link>

                <button
                    style={{
                        display: "flex",
                        alignItems: "center",
                        gap: "0.75rem",
                        padding: "0.6rem 0.85rem",
                        borderRadius: "8px",
                        fontSize: "0.78rem",
                        fontWeight: 600,
                        color: "#94a3b8",
                        background: "transparent",
                        border: "none",
                        cursor: "pointer",
                        textAlign: "left"
                    }}
                >
                    <Settings size={16} color="#64748b" />
                    <span>Settings</span>
                </button>

                <div style={{
                    marginTop: "0.75rem",
                    paddingTop: "0.75rem",
                    borderTop: "1px solid rgba(255, 255, 255, 0.06)",
                    fontSize: "0.65rem",
                    color: "#475569",
                    paddingLeft: "0.5rem"
                }}>
                    <div style={{ fontWeight: 700, color: "#64748b" }}>TAPERADAR X1</div>
                    <div style={{ fontSize: "0.6rem" }}>v1.0.0</div>
                    <div style={{ fontSize: "0.58rem", color: "#334155", marginTop: "0.2rem" }}>Options. Flow. Edge.</div>
                </div>
            </div>
        </aside>
    );
};
