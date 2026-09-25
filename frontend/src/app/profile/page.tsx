import React from "react";
import { UserProfileManager } from "@/components/UserProfileManager";

export const metadata = {
    title: "User Profile & Sound Alerts | TapeRadar X1",
    description: "Institutional trader profile, Web Audio API sound alerts synthesizer, and risk allocation settings.",
};

export default function ProfilePage() {
    return (
        <main className="min-h-screen bg-background">
            <UserProfileManager />
        </main>
    );
}
