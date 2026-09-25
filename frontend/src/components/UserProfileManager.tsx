"use client";

import React, { useState, useEffect } from "react";
import {
    User,
    Volume2,
    VolumeX,
    Key,
    Sliders,
    ShieldCheck,
    Zap,
    Play,
    Check,
    Lock,
    Bell,
    Radio,
    Layers,
    Sparkles,
    Disc,
    Activity,
    Shield,
    Terminal,
    Cpu,
    Wifi,
    Settings,
    Server,
    SlidersHorizontal,
    CheckCircle2
} from "lucide-react";
import {
    loadAudioConfig,
    saveAudioConfig,
    playAlertSound,
    AudioConfig,
    SoundAlertType,
    SoundPack
} from "@/lib/soundAlerts";

export const UserProfileManager: React.FC = () => {
    const [activeTab, setActiveTab] = useState<"AUDIO" | "API_KEYS" | "PREFERENCES">("AUDIO");
    const [mounted, setMounted] = useState<boolean>(false);
    const [audioConfig, setAudioConfig] = useState<AudioConfig>({
        masterEnabled: true,
        volume: 0.7,
        soundPack: "INSTITUTIONAL_SONAR",
        sweepAlert: true,
        wallAlert: true,
        biasFlipAlert: true,
        volatilityAlert: true,
    });

    // Trader Profile Info State
    const [handle, setHandle] = useState<string>("SATOSHI_QUANT");
    const [email, setEmail] = useState<string>("trader@taperadar.io");
    const [savedNotice, setSavedNotice] = useState<boolean>(false);

    // Risk Preferences State
    const [trancheA, setTrancheA] = useState<number>(60);
    const [trancheB, setTrancheB] = useState<number>(40);
    const [maxRisk, setMaxRisk] = useState<number>(1.5);
    const [autoBlotter, setAutoBlotter] = useState<boolean>(true);

    // API Keys State
    const [apiKeys, setApiKeys] = useState([
        { exchange: "Binance Futures", key: "vm89...x7a1", status: "CONNECTED", type: "READ_ONLY", pingMs: 14, ipWhitelist: "192.168.1.100" },
        { exchange: "Coinbase Pro", key: "cb91...k390", status: "CONNECTED", type: "READ_ONLY", pingMs: 22, ipWhitelist: "192.168.1.101" },
        { exchange: "Deribit Options", key: "db77...q912", status: "CONNECTED", type: "READ_ONLY", pingMs: 38, ipWhitelist: "192.168.1.102" },
        { exchange: "OKX Spot", key: "ok44...m009", status: "STANDBY", type: "READ_ONLY", pingMs: 45, ipWhitelist: "192.168.1.103" },
    ]);

    useEffect(() => {
        setAudioConfig(loadAudioConfig());
        setMounted(true);
    }, []);

    useEffect(() => {
        if (mounted) {
            saveAudioConfig(audioConfig);
        }
    }, [audioConfig, mounted]);

    const handleAudioToggle = (key: keyof AudioConfig) => {
        setAudioConfig((prev) => ({
            ...prev,
            [key]: !prev[key],
        }));
    };

    const handleSoundPackChange = (pack: SoundPack) => {
        setAudioConfig((prev) => ({
            ...prev,
            soundPack: pack,
        }));
        playAlertSound("SWEEP", { ...audioConfig, soundPack: pack });
    };

    const handleVolumeChange = (vol: number) => {
        setAudioConfig((prev) => ({
            ...prev,
            volume: vol,
        }));
    };

    const testSound = (type: SoundAlertType) => {
        playAlertSound(type, audioConfig);
    };

    const handleSaveProfile = () => {
        setSavedNotice(true);
        setTimeout(() => setSavedNotice(false), 3000);
    };

    const soundPacksList: { id: SoundPack; label: string; desc: string; icon: React.ReactNode; freqInfo: string }[] = [
        { id: "INSTITUTIONAL_SONAR", label: "INSTITUTIONAL SONAR", desc: "Sub-bass echo (140Hz) + high sonar ping (1.8kHz)", icon: <Disc size={16} />, freqInfo: "180Hz → 1.8kHz" },
        { id: "FUTURISTIC_HUD", label: "FUTURISTIC HUD", desc: "Cybernetic saw-tooth pitch bend + detuned rumble", icon: <Sparkles size={16} />, freqInfo: "800Hz → 3.2kHz" },
        { id: "TACTICAL_MECHANICAL", label: "TACTICAL MECHANICAL", desc: "Metallic relay snaps & multi-stage clicks", icon: <Shield size={16} />, freqInfo: "2.4kHz Relay Transient" },
        { id: "SUBTLE_GLASS", label: "SUBTLE GLASS", desc: "Crystalline glass bell rings & major triad decay", icon: <Activity size={16} />, freqInfo: "1.7kHz Pure Sine" },
    ];

    return (
        <div style={{ padding: "1rem 1.5rem", maxWidth: "1600px", margin: "0 auto", display: "flex", flexDirection: "column", gap: "1rem" }}>

            {/* ── 1. Institutional Trader Identity HUD Banner ── */}
            <div
                style={{
                    backgroundColor: "var(--surface-container-lowest)",
                    border: "1px solid var(--outline-variant)",
                    borderRadius: "6px",
                    padding: "1rem 1.25rem",
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    flexWrap: "wrap",
                    gap: "1rem",
                    boxShadow: "0 4px 20px rgba(0, 0, 0, 0.4)",
                    position: "relative",
                    overflow: "hidden"
                }}
            >
                {/* Subtle Neon Accenting Grid Background */}
                <div style={{ position: "absolute", top: 0, right: 0, width: "300px", height: "100%", background: "radial-gradient(circle at 100% 50%, rgba(0, 227, 143, 0.06), transparent 70%)", pointerEvents: "none" }} />

                {/* Left: Trader Badge & Tier */}
                <div style={{ display: "flex", alignItems: "center", gap: "1.25rem", zIndex: 1 }}>
                    {/* Avatar Icon Box */}
                    <div
                        style={{
                            width: "56px",
                            height: "56px",
                            borderRadius: "6px",
                            backgroundColor: "rgba(0, 227, 143, 0.08)",
                            border: "1px solid var(--primary-fixed-dim)",
                            boxShadow: "0 0 12px rgba(0, 227, 143, 0.2)",
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "center",
                            color: "var(--primary-fixed-dim)",
                            position: "relative"
                        }}
                    >
                        <User size={26} />
                        <div style={{ position: "absolute", bottom: "-3px", right: "-3px", width: "10px", height: "10px", borderRadius: "50%", backgroundColor: "var(--primary-fixed-dim)", boxShadow: "0 0 8px var(--primary-fixed-dim)" }} />
                    </div>

                    <div style={{ display: "flex", flexDirection: "column", gap: "0.25rem" }}>
                        <div style={{ display: "flex", alignItems: "center", gap: "0.6rem" }}>
                            <span className="font-headline-md" style={{ color: "var(--on-surface)", fontWeight: 800, letterSpacing: "0.02em" }}>
                                {handle}
                            </span>
                            <span
                                className="font-mono-data-compact"
                                style={{
                                    padding: "0.15rem 0.6rem",
                                    backgroundColor: "rgba(0, 227, 143, 0.12)",
                                    border: "1px solid rgba(0, 227, 143, 0.3)",
                                    color: "var(--primary-fixed-dim)",
                                    borderRadius: "3px",
                                    fontWeight: 700,
                                    letterSpacing: "0.08em"
                                }}
                            >
                                PRO-CORE v4.8.2 // INSTITUTIONAL TIER
                            </span>
                        </div>
                        <div style={{ display: "flex", alignItems: "center", gap: "1rem" }} className="font-mono-data-compact">
                            <span style={{ color: "var(--on-surface-variant)" }}>ID: <strong style={{ color: "var(--on-surface)" }}>TRADER-QUANT-884</strong></span>
                            <span style={{ color: "var(--outline)" }}>•</span>
                            <span style={{ color: "var(--on-surface-variant)" }}>{email}</span>
                            <span style={{ color: "var(--outline)" }}>•</span>
                            <span style={{ color: "var(--primary-fixed-dim)", display: "flex", alignItems: "center", gap: "0.25rem" }}>
                                <CheckCircle2 size={13} /> VERIFIED QUANT SESSION
                            </span>
                        </div>
                    </div>
                </div>

                {/* Right: Institutional System Status Telemetry */}
                <div style={{ display: "flex", alignItems: "center", gap: "1.25rem", zIndex: 1 }}>
                    <div style={{ padding: "0.4rem 0.8rem", backgroundColor: "var(--surface-container)", borderRadius: "4px", border: "1px solid var(--outline-variant)", display: "flex", flexDirection: "column", alignItems: "flex-end" }}>
                        <span className="font-label-caps" style={{ color: "var(--outline)", fontSize: "0.65rem" }}>CONNECTED VENUES</span>
                        <span className="font-mono-data-compact" style={{ color: "var(--primary-fixed-dim)", fontWeight: 700 }}>
                            3 / 4 WS STREAMS ACTIVE
                        </span>
                    </div>

                    <div style={{ padding: "0.4rem 0.8rem", backgroundColor: "var(--surface-container)", borderRadius: "4px", border: "1px solid var(--outline-variant)", display: "flex", flexDirection: "column", alignItems: "flex-end" }}>
                        <span className="font-label-caps" style={{ color: "var(--outline)", fontSize: "0.65rem" }}>AUDIO ENGINE</span>
                        <span className="font-mono-data-compact" style={{ color: audioConfig.masterEnabled ? "var(--primary-fixed-dim)" : "var(--warn)", fontWeight: 700 }}>
                            {audioConfig.masterEnabled ? "ACTIVE (WEB AUDIO)" : "MUTED"}
                        </span>
                    </div>
                </div>
            </div>

            {/* ── 2. High-Density Navigation Tabs ── */}
            <div style={{ display: "flex", gap: "0.4rem", borderBottom: "1px solid var(--outline-variant)", paddingBottom: "0.4rem" }}>
                <button
                    onClick={() => setActiveTab("AUDIO")}
                    className="font-mono-data-compact"
                    style={{
                        padding: "0.5rem 1.25rem",
                        borderRadius: "4px",
                        border: activeTab === "AUDIO" ? "1px solid var(--primary-fixed-dim)" : "1px solid var(--outline-variant)",
                        backgroundColor: activeTab === "AUDIO" ? "rgba(0, 227, 143, 0.12)" : "var(--surface-container-lowest)",
                        color: activeTab === "AUDIO" ? "var(--primary-fixed-dim)" : "var(--on-surface-variant)",
                        cursor: "pointer",
                        display: "flex",
                        alignItems: "center",
                        gap: "0.5rem",
                        fontWeight: activeTab === "AUDIO" ? 700 : 500,
                        transition: "all 0.15s"
                    }}
                >
                    <Volume2 size={15} />
                    <span>AUDIO ALERTS & TELEMETRY SYNTHESIZER</span>
                </button>

                <button
                    onClick={() => setActiveTab("API_KEYS")}
                    className="font-mono-data-compact"
                    style={{
                        padding: "0.5rem 1.25rem",
                        borderRadius: "4px",
                        border: activeTab === "API_KEYS" ? "1px solid var(--primary-fixed-dim)" : "1px solid var(--outline-variant)",
                        backgroundColor: activeTab === "API_KEYS" ? "rgba(0, 227, 143, 0.12)" : "var(--surface-container-lowest)",
                        color: activeTab === "API_KEYS" ? "var(--primary-fixed-dim)" : "var(--on-surface-variant)",
                        cursor: "pointer",
                        display: "flex",
                        alignItems: "center",
                        gap: "0.5rem",
                        fontWeight: activeTab === "API_KEYS" ? 700 : 500,
                        transition: "all 0.15s"
                    }}
                >
                    <Key size={15} />
                    <span>EXCHANGE API KEYS & LATENCY</span>
                </button>

                <button
                    onClick={() => setActiveTab("PREFERENCES")}
                    className="font-mono-data-compact"
                    style={{
                        padding: "0.5rem 1.25rem",
                        borderRadius: "4px",
                        border: activeTab === "PREFERENCES" ? "1px solid var(--primary-fixed-dim)" : "1px solid var(--outline-variant)",
                        backgroundColor: activeTab === "PREFERENCES" ? "rgba(0, 227, 143, 0.12)" : "var(--surface-container-lowest)",
                        color: activeTab === "PREFERENCES" ? "var(--primary-fixed-dim)" : "var(--on-surface-variant)",
                        cursor: "pointer",
                        display: "flex",
                        alignItems: "center",
                        gap: "0.5rem",
                        fontWeight: activeTab === "PREFERENCES" ? 700 : 500,
                        transition: "all 0.15s"
                    }}
                >
                    <Sliders size={15} />
                    <span>POSITION SIZING & RISK ALLOCATION</span>
                </button>
            </div>

            {/* ── 3. TAB 1: Sound Alerts & Telemetry Audio Engine ── */}
            {activeTab === "AUDIO" && (
                <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>

                    {/* Master Audio Controller Panel */}
                    <div
                        style={{
                            backgroundColor: "var(--surface-container-lowest)",
                            border: "1px solid var(--outline-variant)",
                            borderRadius: "6px",
                            padding: "1rem 1.25rem",
                            display: "flex",
                            flexDirection: "column",
                            gap: "0.85rem"
                        }}
                    >
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                            <div style={{ display: "flex", alignItems: "center", gap: "0.6rem" }}>
                                <div style={{ width: "28px", height: "28px", borderRadius: "4px", backgroundColor: audioConfig.masterEnabled ? "rgba(0, 227, 143, 0.15)" : "rgba(239, 68, 68, 0.15)", display: "flex", alignItems: "center", justifyContent: "center" }}>
                                    {audioConfig.masterEnabled ? <Volume2 size={16} color="var(--primary-fixed-dim)" /> : <VolumeX size={16} color="var(--warn)" />}
                                </div>
                                <div style={{ display: "flex", flexDirection: "column" }}>
                                    <span className="font-headline-sm" style={{ color: "var(--on-surface)", fontWeight: 700 }}>
                                        WEB AUDIO SYNTHESIZER ENGINE
                                    </span>
                                    <span className="font-mono-data-compact" style={{ color: "var(--on-surface-variant)" }}>
                                        Zero-latency real-time market event audio feedback
                                    </span>
                                </div>
                            </div>

                            <button
                                onClick={() => handleAudioToggle("masterEnabled")}
                                className="font-mono-data-compact"
                                style={{
                                    padding: "0.4rem 1.25rem",
                                    borderRadius: "4px",
                                    backgroundColor: audioConfig.masterEnabled ? "var(--primary-fixed-dim)" : "var(--surface-container-high)",
                                    color: audioConfig.masterEnabled ? "#000" : "var(--on-surface)",
                                    border: "none",
                                    fontWeight: 800,
                                    letterSpacing: "0.05em",
                                    cursor: "pointer"
                                }}
                            >
                                {audioConfig.masterEnabled ? "MASTER AUDIO: ONLINE" : "MASTER AUDIO: MUTED"}
                            </button>
                        </div>

                        {/* Master Volume Meter & Slider */}
                        <div style={{ display: "flex", alignItems: "center", gap: "1.25rem", backgroundColor: "var(--surface-container)", padding: "0.6rem 1rem", borderRadius: "4px", border: "1px solid var(--outline-variant)" }}>
                            <span className="font-label-caps" style={{ color: "var(--outline)", width: "140px" }}>OUTPUT VOLUME ({Math.round(audioConfig.volume * 100)}%)</span>
                            <input
                                type="range"
                                min="0"
                                max="1"
                                step="0.05"
                                value={audioConfig.volume}
                                onChange={(e) => handleVolumeChange(parseFloat(e.target.value))}
                                style={{ flex: 1, accentColor: "var(--primary-fixed-dim)", cursor: "pointer" }}
                            />
                            {/* Volume Level Bars Visualizer */}
                            <div style={{ display: "flex", gap: "3px", alignItems: "flex-end", height: "16px" }}>
                                {[0.2, 0.4, 0.6, 0.8, 1.0].map((level, idx) => (
                                    <div
                                        key={idx}
                                        style={{
                                            width: "4px",
                                            height: `${(idx + 1) * 3 + 4}px`,
                                            backgroundColor: audioConfig.volume >= level ? "var(--primary-fixed-dim)" : "var(--surface-container-high)",
                                            borderRadius: "1px"
                                        }}
                                    />
                                ))}
                            </div>
                        </div>
                    </div>

                    {/* ── Sonic Theme / Sound Pack Selector Ribbon ── */}
                    <div
                        style={{
                            backgroundColor: "var(--surface-container-lowest)",
                            border: "1px solid var(--outline-variant)",
                            borderRadius: "6px",
                            padding: "1rem 1.25rem",
                            display: "flex",
                            flexDirection: "column",
                            gap: "0.75rem"
                        }}
                    >
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                                <Sparkles size={16} color="var(--primary-fixed-dim)" />
                                <span className="font-headline-sm" style={{ color: "var(--on-surface)", fontWeight: 700 }}>
                                    SONIC PERSONALITY / OPEN-SOURCE SOUND PACK
                                </span>
                            </div>
                            <span className="font-mono-data-compact" style={{ color: "var(--primary-fixed-dim)", fontWeight: 700 }}>
                                ACTIVE PACK: {audioConfig.soundPack.replace("_", " ")}
                            </span>
                        </div>

                        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))", gap: "0.75rem" }}>
                            {soundPacksList.map((pack) => {
                                const isSelected = audioConfig.soundPack === pack.id;
                                return (
                                    <button
                                        key={pack.id}
                                        onClick={() => handleSoundPackChange(pack.id)}
                                        style={{
                                            padding: "0.75rem 1rem",
                                            borderRadius: "4px",
                                            border: isSelected ? "1px solid var(--primary-fixed-dim)" : "1px solid var(--outline-variant)",
                                            backgroundColor: isSelected ? "rgba(0, 227, 143, 0.08)" : "var(--surface-container)",
                                            display: "flex",
                                            flexDirection: "column",
                                            gap: "0.3rem",
                                            textAlign: "left",
                                            cursor: "pointer",
                                            boxShadow: isSelected ? "0 0 10px rgba(0, 227, 143, 0.15)" : "none",
                                            transition: "all 0.15s"
                                        }}
                                    >
                                        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", color: isSelected ? "var(--primary-fixed-dim)" : "var(--on-surface)" }}>
                                            <div style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                                                {pack.icon}
                                                <span className="font-mono-data-compact" style={{ fontWeight: 700 }}>
                                                    {pack.label}
                                                </span>
                                            </div>
                                            {isSelected && <Check size={15} color="var(--primary-fixed-dim)" />}
                                        </div>
                                        <span className="font-body-sm" style={{ color: "var(--on-surface-variant)", fontSize: "0.7rem", lineHeight: 1.2 }}>
                                            {pack.desc}
                                        </span>
                                        <span className="font-mono-data-compact" style={{ color: isSelected ? "var(--primary-fixed-dim)" : "var(--outline)", fontSize: "0.62rem", marginTop: "0.2rem" }}>
                                            FREQ SPECTRUM: {pack.freqInfo}
                                        </span>
                                    </button>
                                );
                            })}
                        </div>
                    </div>

                    {/* ── 4 Telemetry Event Audio Triggers Grid ── */}
                    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(340px, 1fr))", gap: "1rem" }}>

                        {/* Event 1: Liquidity Sweep */}
                        <div
                            style={{
                                backgroundColor: "var(--surface-container-lowest)",
                                border: "1px solid var(--outline-variant)",
                                borderRadius: "6px",
                                padding: "1rem 1.25rem",
                                display: "flex",
                                flexDirection: "column",
                                gap: "0.75rem"
                            }}
                        >
                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                                <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                                    <Zap size={16} color="var(--primary-fixed-dim)" />
                                    <span className="font-mono-data-compact" style={{ color: "var(--on-surface)", fontWeight: 700 }}>
                                        LIQUIDITY SWEEP ALERTS
                                    </span>
                                </div>
                                <button
                                    onClick={() => handleAudioToggle("sweepAlert")}
                                    style={{
                                        padding: "0.2rem 0.6rem",
                                        borderRadius: "3px",
                                        backgroundColor: audioConfig.sweepAlert ? "rgba(0, 227, 143, 0.15)" : "var(--surface-container-high)",
                                        color: audioConfig.sweepAlert ? "var(--primary-fixed-dim)" : "var(--outline)",
                                        border: "1px solid var(--outline-variant)",
                                        fontSize: "0.68rem",
                                        fontWeight: 700,
                                        cursor: "pointer"
                                    }}
                                >
                                    {audioConfig.sweepAlert ? "ACTIVE" : "MUTED"}
                                </button>
                            </div>

                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", backgroundColor: "var(--surface-container)", padding: "0.4rem 0.6rem", borderRadius: "4px" }}>
                                <span className="font-label-caps" style={{ color: "var(--outline)", fontSize: "0.65rem" }}>TRIGGER THRESHOLD</span>
                                <span className="font-mono-data-compact" style={{ color: "var(--primary-fixed-dim)", fontWeight: 700 }}>&gt; $500K AGGRESSIVE SWEEP</span>
                            </div>

                            <p className="font-body-sm" style={{ color: "var(--on-surface-variant)", fontSize: "0.72rem", lineHeight: 1.3 }}>
                                Synthesizes high-frequency sweep pings whenever aggressive market orders sweep resting limit depth &gt; $500k.
                            </p>

                            <button
                                onClick={() => testSound("SWEEP")}
                                className="font-mono-data-compact"
                                style={{
                                    padding: "0.45rem",
                                    backgroundColor: "var(--surface-container)",
                                    border: "1px solid var(--outline-variant)",
                                    borderRadius: "4px",
                                    color: "var(--primary-fixed-dim)",
                                    cursor: "pointer",
                                    display: "flex",
                                    alignItems: "center",
                                    justifyContent: "center",
                                    gap: "0.4rem",
                                    fontWeight: 700,
                                    transition: "background-color 0.15s"
                                }}
                            >
                                <Play size={13} fill="currentColor" /> TEST SWEEP SOUND ({audioConfig.soundPack.split('_')[0]})
                            </button>
                        </div>

                        {/* Event 2: Passive Limit Wall */}
                        <div
                            style={{
                                backgroundColor: "var(--surface-container-lowest)",
                                border: "1px solid var(--outline-variant)",
                                borderRadius: "6px",
                                padding: "1rem 1.25rem",
                                display: "flex",
                                flexDirection: "column",
                                gap: "0.75rem"
                            }}
                        >
                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                                <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                                    <Layers size={16} color="var(--info)" />
                                    <span className="font-mono-data-compact" style={{ color: "var(--on-surface)", fontWeight: 700 }}>
                                        INSTITUTIONAL WALL BUILD
                                    </span>
                                </div>
                                <button
                                    onClick={() => handleAudioToggle("wallAlert")}
                                    style={{
                                        padding: "0.2rem 0.6rem",
                                        borderRadius: "3px",
                                        backgroundColor: audioConfig.wallAlert ? "rgba(56, 189, 248, 0.15)" : "var(--surface-container-high)",
                                        color: audioConfig.wallAlert ? "var(--info)" : "var(--outline)",
                                        border: "1px solid var(--outline-variant)",
                                        fontSize: "0.68rem",
                                        fontWeight: 700,
                                        cursor: "pointer"
                                    }}
                                >
                                    {audioConfig.wallAlert ? "ACTIVE" : "MUTED"}
                                </button>
                            </div>

                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", backgroundColor: "var(--surface-container)", padding: "0.4rem 0.6rem", borderRadius: "4px" }}>
                                <span className="font-label-caps" style={{ color: "var(--outline)", fontSize: "0.65rem" }}>TRIGGER THRESHOLD</span>
                                <span className="font-mono-data-compact" style={{ color: "var(--info)", fontWeight: 700 }}>&gt; $1.0M PASSIVE WALL</span>
                            </div>

                            <p className="font-body-sm" style={{ color: "var(--on-surface-variant)", fontSize: "0.72rem", lineHeight: 1.3 }}>
                                Synthesizes deep resonant pulses when an institutional resting limit wall &gt; $1.0M is detected in order book depth.
                            </p>

                            <button
                                onClick={() => testSound("WALL")}
                                className="font-mono-data-compact"
                                style={{
                                    padding: "0.45rem",
                                    backgroundColor: "var(--surface-container)",
                                    border: "1px solid var(--outline-variant)",
                                    borderRadius: "4px",
                                    color: "var(--info)",
                                    cursor: "pointer",
                                    display: "flex",
                                    alignItems: "center",
                                    justifyContent: "center",
                                    gap: "0.4rem",
                                    fontWeight: 700,
                                    transition: "background-color 0.15s"
                                }}
                            >
                                <Play size={13} fill="currentColor" /> TEST WALL BUILD SOUND ({audioConfig.soundPack.split('_')[0]})
                            </button>
                        </div>

                        {/* Event 3: Bias Flip */}
                        <div
                            style={{
                                backgroundColor: "var(--surface-container-lowest)",
                                border: "1px solid var(--outline-variant)",
                                borderRadius: "6px",
                                padding: "1rem 1.25rem",
                                display: "flex",
                                flexDirection: "column",
                                gap: "0.75rem"
                            }}
                        >
                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                                <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                                    <Radio size={16} color="var(--primary)" />
                                    <span className="font-mono-data-compact" style={{ color: "var(--on-surface)", fontWeight: 700 }}>
                                        INSTITUTIONAL BIAS FLIP
                                    </span>
                                </div>
                                <button
                                    onClick={() => handleAudioToggle("biasFlipAlert")}
                                    style={{
                                        padding: "0.2rem 0.6rem",
                                        borderRadius: "3px",
                                        backgroundColor: audioConfig.biasFlipAlert ? "rgba(0, 227, 143, 0.15)" : "var(--surface-container-high)",
                                        color: audioConfig.biasFlipAlert ? "var(--primary-fixed-dim)" : "var(--outline)",
                                        border: "1px solid var(--outline-variant)",
                                        fontSize: "0.68rem",
                                        fontWeight: 700,
                                        cursor: "pointer"
                                    }}
                                >
                                    {audioConfig.biasFlipAlert ? "ACTIVE" : "MUTED"}
                                </button>
                            </div>

                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", backgroundColor: "var(--surface-container)", padding: "0.4rem 0.6rem", borderRadius: "4px" }}>
                                <span className="font-label-caps" style={{ color: "var(--outline)", fontSize: "0.65rem" }}>TRIGGER THRESHOLD</span>
                                <span className="font-mono-data-compact" style={{ color: "var(--primary-fixed-dim)", fontWeight: 700 }}>FLOW SHIFT &gt; 65% RATIO</span>
                            </div>

                            <p className="font-body-sm" style={{ color: "var(--on-surface-variant)", fontSize: "0.72rem", lineHeight: 1.3 }}>
                                Plays harmonic tri-tone chimes whenever overall market flow shifts between Bullish Absorption and Bearish Exhaustion.
                            </p>

                            <button
                                onClick={() => testSound("BIAS_FLIP")}
                                className="font-mono-data-compact"
                                style={{
                                    padding: "0.45rem",
                                    backgroundColor: "var(--surface-container)",
                                    border: "1px solid var(--outline-variant)",
                                    borderRadius: "4px",
                                    color: "var(--primary-fixed-dim)",
                                    cursor: "pointer",
                                    display: "flex",
                                    alignItems: "center",
                                    justifyContent: "center",
                                    gap: "0.4rem",
                                    fontWeight: 700,
                                    transition: "background-color 0.15s"
                                }}
                            >
                                <Play size={13} fill="currentColor" /> TEST HARMONIC CHIME ({audioConfig.soundPack.split('_')[0]})
                            </button>
                        </div>

                        {/* Event 4: Volatility Burst */}
                        <div
                            style={{
                                backgroundColor: "var(--surface-container-lowest)",
                                border: "1px solid var(--outline-variant)",
                                borderRadius: "6px",
                                padding: "1rem 1.25rem",
                                display: "flex",
                                flexDirection: "column",
                                gap: "0.75rem"
                            }}
                        >
                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                                <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                                    <Bell size={16} color="var(--warn)" />
                                    <span className="font-mono-data-compact" style={{ color: "var(--on-surface)", fontWeight: 700 }}>
                                        VOLATILITY SPIKE ALERT
                                    </span>
                                </div>
                                <button
                                    onClick={() => handleAudioToggle("volatilityAlert")}
                                    style={{
                                        padding: "0.2rem 0.6rem",
                                        borderRadius: "3px",
                                        backgroundColor: audioConfig.volatilityAlert ? "rgba(245, 158, 11, 0.15)" : "var(--surface-container-high)",
                                        color: audioConfig.volatilityAlert ? "var(--warn)" : "var(--outline)",
                                        border: "1px solid var(--outline-variant)",
                                        fontSize: "0.68rem",
                                        fontWeight: 700,
                                        cursor: "pointer"
                                    }}
                                >
                                    {audioConfig.volatilityAlert ? "ACTIVE" : "MUTED"}
                                </button>
                            </div>

                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", backgroundColor: "var(--surface-container)", padding: "0.4rem 0.6rem", borderRadius: "4px" }}>
                                <span className="font-label-caps" style={{ color: "var(--outline)", fontSize: "0.65rem" }}>TRIGGER THRESHOLD</span>
                                <span className="font-mono-data-compact" style={{ color: "var(--warn)", fontWeight: 700 }}>&gt; 3.0 STDEV VOLATILITY</span>
                            </div>

                            <p className="font-body-sm" style={{ color: "var(--on-surface-variant)", fontSize: "0.72rem", lineHeight: 1.3 }}>
                                Triggers staccato warning bursts when 1-minute price volatility breaks out beyond 3.0 standard deviations.
                            </p>

                            <button
                                onClick={() => testSound("VOLATILITY")}
                                className="font-mono-data-compact"
                                style={{
                                    padding: "0.45rem",
                                    backgroundColor: "var(--surface-container)",
                                    border: "1px solid var(--outline-variant)",
                                    borderRadius: "4px",
                                    color: "var(--warn)",
                                    cursor: "pointer",
                                    display: "flex",
                                    alignItems: "center",
                                    justifyContent: "center",
                                    gap: "0.4rem",
                                    fontWeight: 700,
                                    transition: "background-color 0.15s"
                                }}
                            >
                                <Play size={13} fill="currentColor" /> TEST STACCATO WARNING ({audioConfig.soundPack.split('_')[0]})
                            </button>
                        </div>

                    </div>
                </div>
            )}

            {/* ── 4. TAB 2: API Keys Management (Read-Only) ── */}
            {activeTab === "API_KEYS" && (
                <div
                    style={{
                        backgroundColor: "var(--surface-container-lowest)",
                        border: "1px solid var(--outline-variant)",
                        borderRadius: "6px",
                        padding: "1.25rem",
                        display: "flex",
                        flexDirection: "column",
                        gap: "1rem"
                    }}
                >
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                            <ShieldCheck size={18} color="var(--primary-fixed-dim)" />
                            <span className="font-headline-sm" style={{ color: "var(--on-surface)", fontWeight: 700 }}>
                                CONNECTED EXCHANGE API KEYS (READ-ONLY TELEMETRY)
                            </span>
                        </div>
                        <span className="font-mono-data-compact" style={{ color: "var(--primary-fixed-dim)", backgroundColor: "rgba(0, 227, 143, 0.12)", padding: "0.2rem 0.6rem", borderRadius: "3px", fontWeight: 700 }}>
                            🔒 256-BIT ENCRYPTED • ZERO TRADE/WITHDRAWAL PERMISSIONS
                        </span>
                    </div>

                    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
                        {apiKeys.map((k) => (
                            <div
                                key={k.exchange}
                                style={{
                                    padding: "0.85rem 1rem",
                                    backgroundColor: "var(--surface-container)",
                                    border: "1px solid var(--outline-variant)",
                                    borderRadius: "4px",
                                    display: "flex",
                                    justifyContent: "space-between",
                                    alignItems: "center"
                                }}
                            >
                                <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
                                    <div style={{ width: "32px", height: "32px", borderRadius: "4px", backgroundColor: "var(--surface-container-high)", display: "flex", alignItems: "center", justifyContent: "center", color: "var(--outline)" }}>
                                        <Lock size={16} />
                                    </div>
                                    <div style={{ display: "flex", flexDirection: "column" }}>
                                        <span className="font-mono-data-compact" style={{ color: "var(--on-surface)", fontWeight: 700, fontSize: "0.85rem" }}>
                                            {k.exchange}
                                        </span>
                                        <span className="font-mono-data-compact" style={{ color: "var(--on-surface-variant)", fontSize: "0.72rem" }}>
                                            KEY HASH: {k.key} • WHITELIST: {k.ipWhitelist}
                                        </span>
                                    </div>
                                </div>

                                <div style={{ display: "flex", alignItems: "center", gap: "1.25rem" }}>
                                    <div style={{ display: "flex", alignItems: "center", gap: "0.35rem" }} className="font-mono-data-compact">
                                        <span style={{ width: "6px", height: "6px", borderRadius: "50%", backgroundColor: k.status === "CONNECTED" ? "var(--primary-fixed-dim)" : "var(--warn)", boxShadow: k.status === "CONNECTED" ? "0 0 6px var(--primary-fixed-dim)" : "none" }} />
                                        <span style={{ color: "var(--on-surface-variant)" }}>LATENCY:</span>
                                        <span style={{ color: k.status === "CONNECTED" ? "var(--primary-fixed-dim)" : "var(--warn)", fontWeight: 700 }}>{k.pingMs}ms</span>
                                    </div>

                                    <span
                                        className="font-mono-data-compact"
                                        style={{
                                            padding: "0.2rem 0.6rem",
                                            backgroundColor: k.status === "CONNECTED" ? "rgba(0, 227, 143, 0.12)" : "rgba(245, 158, 11, 0.12)",
                                            color: k.status === "CONNECTED" ? "var(--primary-fixed-dim)" : "var(--warn)",
                                            border: "1px solid var(--outline-variant)",
                                            borderRadius: "3px",
                                            fontWeight: 700
                                        }}
                                    >
                                        {k.status} ({k.type})
                                    </span>
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            )}

            {/* ── 5. TAB 3: Risk Allocation & Terminal Preferences ── */}
            {activeTab === "PREFERENCES" && (
                <div
                    style={{
                        backgroundColor: "var(--surface-container-lowest)",
                        border: "1px solid var(--outline-variant)",
                        borderRadius: "6px",
                        padding: "1.25rem",
                        display: "flex",
                        flexDirection: "column",
                        gap: "1.25rem"
                    }}
                >
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                        <span className="font-headline-sm" style={{ color: "var(--on-surface)", fontWeight: 700 }}>
                            POSITION SIZING & TERMINAL RISK PREFERENCES
                        </span>
                        <span className="font-mono-data-compact" style={{ color: "var(--on-surface-variant)" }}>
                            Automated tranche split parameters
                        </span>
                    </div>

                    {/* Tranche Allocation Proportion Bar */}
                    <div style={{ backgroundColor: "var(--surface-container)", padding: "1rem", borderRadius: "4px", border: "1px solid var(--outline-variant)", display: "flex", flexDirection: "column", gap: "0.75rem" }}>
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }} className="font-mono-data-compact">
                            <span style={{ color: "var(--primary-fixed-dim)", fontWeight: 700 }}>TRANCHE A (INITIAL BREAKOUT): {trancheA}%</span>
                            <span style={{ color: "var(--info)", fontWeight: 700 }}>TRANCHE B (PULLBACK / ADD): {trancheB}%</span>
                        </div>

                        {/* Visual Split Bar */}
                        <div style={{ height: "8px", backgroundColor: "var(--surface-container-high)", borderRadius: "4px", display: "flex", overflow: "hidden" }}>
                            <div style={{ width: `${trancheA}%`, backgroundColor: "var(--primary-fixed-dim)", transition: "width 0.2s" }} />
                            <div style={{ width: `${trancheB}%`, backgroundColor: "var(--info)", transition: "width 0.2s" }} />
                        </div>
                    </div>

                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>
                        {/* Tranche Allocation Split Input */}
                        <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem", backgroundColor: "var(--surface-container)", padding: "1rem", borderRadius: "4px", border: "1px solid var(--outline-variant)" }}>
                            <span className="font-label-caps" style={{ color: "var(--outline)" }}>TRANCHE ALLOCATION SPLIT (%)</span>
                            <div style={{ display: "flex", gap: "1rem" }}>
                                <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: "0.2rem" }}>
                                    <span className="font-mono-data-compact" style={{ color: "var(--primary-fixed-dim)" }}>TRANCHE A (%)</span>
                                    <input
                                        type="number"
                                        value={trancheA}
                                        onChange={(e) => {
                                            const val = Math.min(100, Math.max(0, Number(e.target.value)));
                                            setTrancheA(val);
                                            setTrancheB(100 - val);
                                        }}
                                        style={{ padding: "0.5rem", backgroundColor: "var(--surface-container-lowest)", border: "1px solid var(--outline-variant)", borderRadius: "4px", color: "#fff", fontFamily: "var(--font-mono)" }}
                                    />
                                </div>
                                <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: "0.2rem" }}>
                                    <span className="font-mono-data-compact" style={{ color: "var(--info)" }}>TRANCHE B (%)</span>
                                    <input
                                        type="number"
                                        value={trancheB}
                                        onChange={(e) => {
                                            const val = Math.min(100, Math.max(0, Number(e.target.value)));
                                            setTrancheB(val);
                                            setTrancheA(100 - val);
                                        }}
                                        style={{ padding: "0.5rem", backgroundColor: "var(--surface-container-lowest)", border: "1px solid var(--outline-variant)", borderRadius: "4px", color: "#fff", fontFamily: "var(--font-mono)" }}
                                    />
                                </div>
                            </div>
                        </div>

                        {/* Max Risk % Input */}
                        <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem", backgroundColor: "var(--surface-container)", padding: "1rem", borderRadius: "4px", border: "1px solid var(--outline-variant)" }}>
                            <span className="font-label-caps" style={{ color: "var(--outline)" }}>MAX RISK PER TRADE (% OF TOTAL EQUITY)</span>
                            <input
                                type="number"
                                step="0.1"
                                value={maxRisk}
                                onChange={(e) => setMaxRisk(parseFloat(e.target.value) || 0)}
                                style={{ padding: "0.5rem", backgroundColor: "var(--surface-container-lowest)", border: "1px solid var(--outline-variant)", borderRadius: "4px", color: "#fff", fontFamily: "var(--font-mono)" }}
                            />
                            <span className="font-mono-data-compact" style={{ color: "var(--on-surface-variant)", fontSize: "0.7rem" }}>
                                Simulated Max Stop Loss Drawdown: <strong style={{ color: "var(--warn)" }}>-${(100000 * (maxRisk / 100)).toLocaleString()}</strong> (on $100k equity)
                            </span>
                        </div>
                    </div>

                    <div style={{ display: "flex", justifyContent: "flex-end", marginTop: "0.5rem" }}>
                        <button
                            onClick={handleSaveProfile}
                            className="font-mono-data-compact"
                            style={{
                                padding: "0.6rem 1.75rem",
                                backgroundColor: "var(--primary-fixed-dim)",
                                color: "#000",
                                border: "none",
                                borderRadius: "4px",
                                fontWeight: 800,
                                letterSpacing: "0.05em",
                                cursor: "pointer",
                                display: "flex",
                                alignItems: "center",
                                gap: "0.4rem",
                                boxShadow: "0 0 12px rgba(0, 227, 143, 0.25)"
                            }}
                        >
                            {savedNotice ? <Check size={16} /> : null}
                            {savedNotice ? "PREFERENCES SAVED" : "SAVE RISK PARAMETERS"}
                        </button>
                    </div>
                </div>
            )}

        </div>
    );
};
