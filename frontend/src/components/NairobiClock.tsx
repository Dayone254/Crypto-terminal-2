"use client";

import React, { useEffect, useState } from "react";

export function NairobiClock() {
    const [time, setTime] = useState<string>("");

    useEffect(() => {
        const updateTime = () => {
            setTime(new Date().toLocaleTimeString("en-KE", { timeZone: "Africa/Nairobi", hour12: false }));
        };
        updateTime();
        const interval = setInterval(updateTime, 1000);
        return () => clearInterval(interval);
    }, []);

    // Return empty space or a skeleton until the first client-side mount resolves to avoid hydration mismatch
    if (!time) {
        return <span style={{ opacity: 0 }}>00:00:00</span>;
    }

    return <span>{time}</span>;
}
