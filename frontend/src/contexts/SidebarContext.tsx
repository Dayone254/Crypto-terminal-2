"use client";

import React, { createContext, useContext, useState, useEffect } from "react";

interface SidebarContextType {
    isOpen: boolean;
    toggleSidebar: () => void;
    sidebarWidth: number;
}

const SidebarContext = createContext<SidebarContextType | undefined>(undefined);

export function SidebarProvider({ children }: { children: React.ReactNode }) {
    const [isOpen, setIsOpen] = useState(true);
    const sidebarWidth = isOpen ? 256 : 68;

    useEffect(() => {
        document.documentElement.style.setProperty('--sidebar-width', `${sidebarWidth}px`);
        document.documentElement.style.setProperty('--sidebar-transition', 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)');
    }, [sidebarWidth]);

    return (
        <SidebarContext.Provider value={{ isOpen, toggleSidebar: () => setIsOpen(!isOpen), sidebarWidth }}>
            {children}
        </SidebarContext.Provider>
    );
}

export function useSidebar() {
    const context = useContext(SidebarContext);
    if (context === undefined) {
        throw new Error("useSidebar must be used within a SidebarProvider");
    }
    return context;
}
