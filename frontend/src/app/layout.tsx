import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
    title: "Top Picker Terminal",
    description: "Crypto market scanner — Coinbase USD spot pairs. COILED / EARLY / CHASE detection with limit ladders.",
};

import { SidebarProvider } from "@/contexts/SidebarContext";

export default function RootLayout({ children }: { children: React.ReactNode }) {
    return (
        <html lang="en">
            <body>
                <SidebarProvider>
                    {children}
                </SidebarProvider>
            </body>
        </html>
    );
}
