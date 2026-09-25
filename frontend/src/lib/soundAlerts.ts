"use client";

export type SoundAlertType = "SWEEP" | "WALL" | "BIAS_FLIP" | "VOLATILITY";

export type SoundPack = "INSTITUTIONAL_SONAR" | "FUTURISTIC_HUD" | "TACTICAL_MECHANICAL" | "SUBTLE_GLASS";

export interface AudioConfig {
    masterEnabled: boolean;
    volume: number; // 0.0 to 1.0
    soundPack: SoundPack;
    sweepAlert: boolean;
    wallAlert: boolean;
    biasFlipAlert: boolean;
    volatilityAlert: boolean;
}

const DEFAULT_AUDIO_CONFIG: AudioConfig = {
    masterEnabled: true,
    volume: 0.7,
    soundPack: "INSTITUTIONAL_SONAR",
    sweepAlert: true,
    wallAlert: true,
    biasFlipAlert: true,
    volatilityAlert: true,
};

const STORAGE_KEY = "taperadar_audio_config";

export function loadAudioConfig(): AudioConfig {
    if (typeof window === "undefined") return DEFAULT_AUDIO_CONFIG;
    try {
        const raw = localStorage.getItem(STORAGE_KEY);
        if (raw) {
            return { ...DEFAULT_AUDIO_CONFIG, ...JSON.parse(raw) };
        }
    } catch {
        // Fallback
    }
    return DEFAULT_AUDIO_CONFIG;
}

export function saveAudioConfig(config: AudioConfig): void {
    if (typeof window === "undefined") return;
    try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(config));
    } catch {
        // Fallback
    }
}

let audioCtx: AudioContext | null = null;

function getAudioContext(): AudioContext | null {
    if (typeof window === "undefined") return null;
    if (!audioCtx) {
        const AudioContextClass = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
        if (AudioContextClass) {
            audioCtx = new AudioContextClass();
        }
    }
    if (audioCtx && audioCtx.state === "suspended") {
        audioCtx.resume();
    }
    return audioCtx;
}

export function playAlertSound(type: SoundAlertType, customConfig?: AudioConfig): void {
    const config = customConfig || loadAudioConfig();
    if (!config.masterEnabled) return;

    if (type === "SWEEP" && !config.sweepAlert) return;
    if (type === "WALL" && !config.wallAlert) return;
    if (type === "BIAS_FLIP" && !config.biasFlipAlert) return;
    if (type === "VOLATILITY" && !config.volatilityAlert) return;

    const ctx = getAudioContext();
    if (!ctx) return;

    const masterGain = ctx.createGain();
    masterGain.gain.value = config.volume;
    masterGain.connect(ctx.destination);

    const now = ctx.currentTime;
    const pack = config.soundPack || "INSTITUTIONAL_SONAR";

    if (pack === "INSTITUTIONAL_SONAR") {
        switch (type) {
            case "SWEEP": {
                // High-pitched double sonar ping (1200Hz -> 1800Hz)
                const osc1 = ctx.createOscillator();
                const gain1 = ctx.createGain();
                osc1.type = "sine";
                osc1.frequency.setValueAtTime(1200, now);
                osc1.frequency.exponentialRampToValueAtTime(1800, now + 0.08);
                gain1.gain.setValueAtTime(0.4, now);
                gain1.gain.exponentialRampToValueAtTime(0.001, now + 0.12);
                osc1.connect(gain1);
                gain1.connect(masterGain);
                osc1.start(now);
                osc1.stop(now + 0.12);

                const osc2 = ctx.createOscillator();
                const gain2 = ctx.createGain();
                osc2.type = "sine";
                osc2.frequency.setValueAtTime(1500, now + 0.08);
                osc2.frequency.exponentialRampToValueAtTime(2200, now + 0.18);
                gain2.gain.setValueAtTime(0.5, now + 0.08);
                gain2.gain.exponentialRampToValueAtTime(0.001, now + 0.22);
                osc2.connect(gain2);
                gain2.connect(masterGain);
                osc2.start(now + 0.08);
                osc2.stop(now + 0.22);
                break;
            }
            case "WALL": {
                // Deep resonant low-frequency sonar pulse (180Hz -> 140Hz)
                const osc = ctx.createOscillator();
                const gain = ctx.createGain();
                osc.type = "triangle";
                osc.frequency.setValueAtTime(180, now);
                osc.frequency.exponentialRampToValueAtTime(140, now + 0.25);
                gain.gain.setValueAtTime(0.6, now);
                gain.gain.exponentialRampToValueAtTime(0.001, now + 0.28);
                osc.connect(gain);
                gain.connect(masterGain);
                osc.start(now);
                osc.stop(now + 0.28);
                break;
            }
            case "BIAS_FLIP": {
                // Harmonic arpeggio chime (440Hz -> 660Hz -> 880Hz)
                [440, 660, 880].forEach((f, idx) => {
                    const osc = ctx.createOscillator();
                    const gain = ctx.createGain();
                    const startTime = now + idx * 0.06;
                    osc.type = "sine";
                    osc.frequency.setValueAtTime(f, startTime);
                    gain.gain.setValueAtTime(0.35, startTime);
                    gain.gain.exponentialRampToValueAtTime(0.001, startTime + 0.15);
                    osc.connect(gain);
                    gain.connect(masterGain);
                    osc.start(startTime);
                    osc.stop(startTime + 0.15);
                });
                break;
            }
            case "VOLATILITY": {
                // Staccato alert warning pulse (900Hz x 3)
                for (let i = 0; i < 3; i++) {
                    const osc = ctx.createOscillator();
                    const gain = ctx.createGain();
                    const startTime = now + i * 0.07;
                    osc.type = "square";
                    osc.frequency.setValueAtTime(900, startTime);
                    gain.gain.setValueAtTime(0.2, startTime);
                    gain.gain.exponentialRampToValueAtTime(0.001, startTime + 0.05);
                    osc.connect(gain);
                    gain.connect(masterGain);
                    osc.start(startTime);
                    osc.stop(startTime + 0.05);
                }
                break;
            }
        }
    } else if (pack === "FUTURISTIC_HUD") {
        switch (type) {
            case "SWEEP": {
                // Cybernetic saw-toothed pitch bend (800Hz -> 3200Hz)
                const osc = ctx.createOscillator();
                const gain = ctx.createGain();
                osc.type = "sawtooth";
                osc.frequency.setValueAtTime(800, now);
                osc.frequency.exponentialRampToValueAtTime(3200, now + 0.15);
                gain.gain.setValueAtTime(0.3, now);
                gain.gain.exponentialRampToValueAtTime(0.001, now + 0.18);
                osc.connect(gain);
                gain.connect(masterGain);
                osc.start(now);
                osc.stop(now + 0.18);
                break;
            }
            case "WALL": {
                // Dual detuned synth rumble (110Hz + 114Hz)
                [110, 114].forEach((f) => {
                    const osc = ctx.createOscillator();
                    const gain = ctx.createGain();
                    osc.type = "sawtooth";
                    osc.frequency.setValueAtTime(f, now);
                    gain.gain.setValueAtTime(0.35, now);
                    gain.gain.exponentialRampToValueAtTime(0.001, now + 0.35);
                    osc.connect(gain);
                    gain.connect(masterGain);
                    osc.start(now);
                    osc.stop(now + 0.35);
                });
                break;
            }
            case "BIAS_FLIP": {
                // Sci-fi synth chime sweep (523Hz -> 1046Hz -> 2093Hz)
                [523.25, 1046.5, 2093.0].forEach((f, idx) => {
                    const osc = ctx.createOscillator();
                    const gain = ctx.createGain();
                    const startTime = now + idx * 0.05;
                    osc.type = "triangle";
                    osc.frequency.setValueAtTime(f, startTime);
                    gain.gain.setValueAtTime(0.4, startTime);
                    gain.gain.exponentialRampToValueAtTime(0.001, startTime + 0.2);
                    osc.connect(gain);
                    gain.connect(masterGain);
                    osc.start(startTime);
                    osc.stop(startTime + 0.2);
                });
                break;
            }
            case "VOLATILITY": {
                // High-tech laser strobe pulse
                for (let i = 0; i < 4; i++) {
                    const osc = ctx.createOscillator();
                    const gain = ctx.createGain();
                    const startTime = now + i * 0.05;
                    osc.type = "sawtooth";
                    osc.frequency.setValueAtTime(1400 - i * 150, startTime);
                    gain.gain.setValueAtTime(0.25, startTime);
                    gain.gain.exponentialRampToValueAtTime(0.001, startTime + 0.04);
                    osc.connect(gain);
                    gain.connect(masterGain);
                    osc.start(startTime);
                    osc.stop(startTime + 0.04);
                }
                break;
            }
        }
    } else if (pack === "TACTICAL_MECHANICAL") {
        switch (type) {
            case "SWEEP": {
                // Metallic click burst (sharp noise/square click)
                const osc = ctx.createOscillator();
                const gain = ctx.createGain();
                osc.type = "square";
                osc.frequency.setValueAtTime(2400, now);
                osc.frequency.exponentialRampToValueAtTime(600, now + 0.03);
                gain.gain.setValueAtTime(0.5, now);
                gain.gain.exponentialRampToValueAtTime(0.001, now + 0.04);
                osc.connect(gain);
                gain.connect(masterGain);
                osc.start(now);
                osc.stop(now + 0.04);
                break;
            }
            case "WALL": {
                // Mechanical latch clack (heavy dual transient)
                [220, 880].forEach((f, idx) => {
                    const osc = ctx.createOscillator();
                    const gain = ctx.createGain();
                    const startTime = now + idx * 0.04;
                    osc.type = "triangle";
                    osc.frequency.setValueAtTime(f, startTime);
                    gain.gain.setValueAtTime(0.4, startTime);
                    gain.gain.exponentialRampToValueAtTime(0.001, startTime + 0.08);
                    osc.connect(gain);
                    gain.connect(masterGain);
                    osc.start(startTime);
                    osc.stop(startTime + 0.08);
                });
                break;
            }
            case "BIAS_FLIP": {
                // Tactical relay flip click sequence
                [350, 700, 1400].forEach((f, idx) => {
                    const osc = ctx.createOscillator();
                    const gain = ctx.createGain();
                    const startTime = now + idx * 0.04;
                    osc.type = "square";
                    osc.frequency.setValueAtTime(f, startTime);
                    gain.gain.setValueAtTime(0.3, startTime);
                    gain.gain.exponentialRampToValueAtTime(0.001, startTime + 0.05);
                    osc.connect(gain);
                    gain.connect(masterGain);
                    osc.start(startTime);
                    osc.stop(startTime + 0.05);
                });
                break;
            }
            case "VOLATILITY": {
                // Heavy mechanical alarm click
                for (let i = 0; i < 3; i++) {
                    const osc = ctx.createOscillator();
                    const gain = ctx.createGain();
                    const startTime = now + i * 0.06;
                    osc.type = "sawtooth";
                    osc.frequency.setValueAtTime(1100, startTime);
                    gain.gain.setValueAtTime(0.35, startTime);
                    gain.gain.exponentialRampToValueAtTime(0.001, startTime + 0.03);
                    osc.connect(gain);
                    gain.connect(masterGain);
                    osc.start(startTime);
                    osc.stop(startTime + 0.03);
                }
                break;
            }
        }
    } else if (pack === "SUBTLE_GLASS") {
        switch (type) {
            case "SWEEP": {
                // Soft crystalline bell ring (1760Hz / A6)
                const osc = ctx.createOscillator();
                const gain = ctx.createGain();
                osc.type = "sine";
                osc.frequency.setValueAtTime(1760, now);
                gain.gain.setValueAtTime(0.4, now);
                gain.gain.exponentialRampToValueAtTime(0.001, now + 0.35);
                osc.connect(gain);
                gain.connect(masterGain);
                osc.start(now);
                osc.stop(now + 0.35);
                break;
            }
            case "WALL": {
                // Soft low glass hum (220Hz / A3)
                const osc = ctx.createOscillator();
                const gain = ctx.createGain();
                osc.type = "sine";
                osc.frequency.setValueAtTime(220, now);
                gain.gain.setValueAtTime(0.5, now);
                gain.gain.exponentialRampToValueAtTime(0.001, now + 0.45);
                osc.connect(gain);
                gain.connect(masterGain);
                osc.start(now);
                osc.stop(now + 0.45);
                break;
            }
            case "BIAS_FLIP": {
                // Crystalline glass major triad (523Hz -> 659Hz -> 784Hz)
                [523.25, 659.25, 783.99].forEach((f, idx) => {
                    const osc = ctx.createOscillator();
                    const gain = ctx.createGain();
                    const startTime = now + idx * 0.07;
                    osc.type = "sine";
                    osc.frequency.setValueAtTime(f, startTime);
                    gain.gain.setValueAtTime(0.35, startTime);
                    gain.gain.exponentialRampToValueAtTime(0.001, startTime + 0.4);
                    osc.connect(gain);
                    gain.connect(masterGain);
                    osc.start(startTime);
                    osc.stop(startTime + 0.4);
                });
                break;
            }
            case "VOLATILITY": {
                // Gentle warning glass chime
                for (let i = 0; i < 3; i++) {
                    const osc = ctx.createOscillator();
                    const gain = ctx.createGain();
                    const startTime = now + i * 0.08;
                    osc.type = "sine";
                    osc.frequency.setValueAtTime(1318.51, startTime);
                    gain.gain.setValueAtTime(0.3, startTime);
                    gain.gain.exponentialRampToValueAtTime(0.001, startTime + 0.15);
                    osc.connect(gain);
                    gain.connect(masterGain);
                    osc.start(startTime);
                    osc.stop(startTime + 0.15);
                }
                break;
            }
        }
    }
}
