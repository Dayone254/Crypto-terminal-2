"use client";

import React, { useEffect, useState } from "react";
import { Send, CheckCircle2, XCircle, Loader2, Bell } from "lucide-react";
import { apiFetch } from "@/lib/api";

export const TelegramSettings: React.FC = () => {
    const [token, setToken] = useState("");
    const [chatId, setChatId] = useState("");
    const [status, setStatus] = useState<"idle" | "saving" | "testing" | "ok" | "error">("idle");
    const [message, setMessage] = useState("");
    const [configured, setConfigured] = useState(false);

    useEffect(() => {
        apiFetch("/api/v1/config")
            .then((r) => r.json())
            .then((d) => {
                setConfigured(d.telegram_configured);
                if (d.telegram_chat_id) setChatId(d.telegram_chat_id);
            })
            .catch(() => { });
    }, []);

    const save = async () => {
        setStatus("saving");
        setMessage("");
        try {
            const res = await apiFetch("/api/v1/config/telegram", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ telegram_bot_token: token, telegram_chat_id: chatId }),
            });
            const data = await res.json();
            setStatus(data.ok ? "ok" : "error");
            setMessage(data.message);
            if (data.ok) setConfigured(true);
        } catch {
            setStatus("error");
            setMessage("Failed to reach backend.");
        }
    };

    const test = async () => {
        setStatus("testing");
        setMessage("");
        try {
            const res = await apiFetch("/api/v1/config/telegram/test", { method: "POST" });
            const data = await res.json();
            setStatus(data.ok ? "ok" : "error");
            setMessage(data.message);
        } catch {
            setStatus("error");
            setMessage("Failed to reach backend.");
        }
    };

    return (
        <div style={{ background: "#080A0F", borderRadius: 0, border: "none", overflow: "hidden" }}>

            <div style={{ background: "#0B0F19", padding: "1rem 1.25rem", borderBottom: "none", display: "flex", alignItems: "center", gap: "0.6rem" }}>
                <Bell size={16} color="var(--accent-cyan)" />
                <h2 style={{ fontSize: "0.85rem", fontWeight: 800, margin: 0, color: "#E2E8F0", textTransform: "uppercase", letterSpacing: "0.04em" }}>
                    Push Alerts
                </h2>
                {configured && (
                    <span style={{ marginLeft: "auto", fontSize: "0.65rem", color: "#10B981", fontWeight: 700, background: "rgba(16,185,129,0.1)", padding: "0.2rem 0.5rem", borderRadius: 0, border: "none" }}>
                        ● ACTIVE
                    </span>
                )}
            </div>

            <div style={{ padding: "1rem 1.25rem", display: "flex", flexDirection: "column", gap: "0.75rem" }}>
                <p style={{ margin: 0, fontSize: "0.75rem", color: "var(--text-dim)", lineHeight: 1.6 }}>
                    Connect a Telegram bot to receive instant alerts when high-conviction setups fire.
                </p>

                <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                    <label style={{ fontSize: "0.65rem", fontWeight: 800, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.05em" }}>
                        Bot Token
                    </label>
                    <input
                        type="password"
                        placeholder="123456789:ABC..."
                        value={token}
                        onChange={(e) => setToken(e.target.value)}
                        style={{
                            background: "rgba(255,255,255,0.04)",
                            border: "none",
                            borderRadius: 0,
                            padding: "0.6rem 0.8rem",
                            color: "#E2E8F0",
                            fontSize: "0.8rem",
                            fontFamily: "var(--font-jetbrains)",
                            outline: "none",
                            width: "100%",
                            boxSizing: "border-box",
                        }}
                    />
                </div>

                <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                    <label style={{ fontSize: "0.65rem", fontWeight: 800, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.05em" }}>
                        Chat ID
                    </label>
                    <input
                        type="text"
                        placeholder="-100123456789"
                        value={chatId}
                        onChange={(e) => setChatId(e.target.value)}
                        style={{
                            background: "rgba(255,255,255,0.04)",
                            border: "none",
                            borderRadius: 0,
                            padding: "0.6rem 0.8rem",
                            color: "#E2E8F0",
                            fontSize: "0.8rem",
                            fontFamily: "var(--font-jetbrains)",
                            outline: "none",
                            width: "100%",
                            boxSizing: "border-box",
                        }}
                    />
                </div>

                <div style={{ display: "flex", gap: "0.5rem" }}>
                    <button
                        onClick={save}
                        disabled={!token || !chatId || status === "saving"}
                        style={{
                            flex: 1,
                            background: "rgba(6,182,212,0.15)",
                            border: "none",
                            color: "#06B6D4",
                            padding: "0.6rem",
                            borderRadius: 0,
                            fontSize: "0.75rem",
                            fontWeight: 800,
                            cursor: "pointer",
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "center",
                            gap: "0.4rem",
                        }}
                    >
                        {status === "saving" ? <Loader2 size={14} className="spin" /> : <Send size={14} />}
                        Save
                    </button>
                    <button
                        onClick={test}
                        disabled={!configured || status === "testing"}
                        style={{
                            flex: 1,
                            background: "rgba(16,185,129,0.1)",
                            border: "none",
                            color: "#10B981",
                            padding: "0.6rem",
                            borderRadius: 0,
                            fontSize: "0.75rem",
                            fontWeight: 800,
                            cursor: "pointer",
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "center",
                            gap: "0.4rem",
                            opacity: !configured ? 0.4 : 1,
                        }}
                    >
                        {status === "testing" ? <Loader2 size={14} className="spin" /> : <CheckCircle2 size={14} />}
                        Test
                    </button>
                </div>

                {message && (
                    <div style={{
                        display: "flex",
                        alignItems: "center",
                        gap: "0.5rem",
                        padding: "0.6rem 0.8rem",
                        borderRadius: 0,
                        background: status === "ok" ? "rgba(16,185,129,0.08)" : "rgba(244,63,94,0.08)",
                        border: `1px solid ${status === "ok" ? "rgba(16,185,129,0.2)" : "rgba(244,63,94,0.2)"}`,
                        fontSize: "0.75rem",
                        color: status === "ok" ? "#10B981" : "#F43F5E",
                    }}>
                        {status === "ok" ? <CheckCircle2 size={13} /> : <XCircle size={13} />}
                        {message}
                    </div>
                )}

                <p style={{ margin: 0, fontSize: "0.65rem", color: "var(--text-dim)", lineHeight: 1.5 }}>
                    Create a bot via <strong style={{ color: "var(--text-muted)" }}>@BotFather</strong> on Telegram, then add it to your channel and copy the Chat ID.
                </p>
            </div>
        </div>
    );
};
