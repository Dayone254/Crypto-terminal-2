'use client';

import React, { useState, useEffect } from 'react';
import { apiFetch } from '@/lib/api';
import { Shield, Zap, TrendingUp, TrendingDown, RefreshCw, Layers, ArrowDownRight, Search } from 'lucide-react';

interface BTCRegime {
    regime: 'RISK_ON' | 'RISK_OFF' | 'NEUTRAL';
    score: number;
    reason: string;
    net_gex_millions: number;
    gamma_flip_dist_pct: number;
}

interface RSSummary {
    total_universe: number;
    long_leaders_count: number;
    short_laggards_count: number;
}

interface RSCandidate {
    product_id: string;
    last_price: number;
    day_change_pct: number;
    rs_raw: number;
    rs_z_score: number;
    rs_signal: string;
    rs_signal_label: string;
}

interface RSMatrixData {
    btc_regime: BTCRegime;
    summary: RSSummary;
    candidates: RSCandidate[];
}

interface AltcoinRSRadarProps {
    onSelectSymbol?: (symbol: string) => void;
}

export const AltcoinRSRadar: React.FC<AltcoinRSRadarProps> = ({ onSelectSymbol }) => {
    const [data, setData] = useState<RSMatrixData | null>(null);
    const [loading, setLoading] = useState<boolean>(true);
    const [error, setError] = useState<string | null>(null);
    const [filterSignal, setFilterSignal] = useState<string>('ALL');
    const [searchTerm, setSearchTerm] = useState<string>('');

    const fetchRSMatrix = async () => {
        try {
            setLoading(true);
            setError(null);
            const res = await apiFetch('/api/v1/markets/rs-matrix');
            if (!res.ok) {
                throw new Error(`Failed to load RS matrix: HTTP ${res.status}`);
            }
            const jsonData: RSMatrixData = await res.json();
            setData(jsonData);
        } catch (err: any) {
            console.error('Error fetching RS matrix:', err);
            setError(err.message || 'Failed to fetch Relative Strength matrix');
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchRSMatrix();
        const interval = setInterval(fetchRSMatrix, 15000);
        return () => clearInterval(interval);
    }, []);

    if (loading && !data) {
        return (
            <div style={{
                padding: '3rem',
                background: 'var(--surface-1)',
                border: '1px solid var(--line)',
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '1rem',
                color: 'var(--text-3)'
            }}>
                <RefreshCw style={{ width: 24, height: 24, animation: 'spin 1s linear infinite', color: 'var(--info)' }} />
                <span style={{ fontSize: 'var(--fs-sm)', fontWeight: 600, fontFamily: 'var(--font-mono)' }}>
                    COMPUTING BTC REGIME & ALTCOIN RS MATRIX...
                </span>
            </div>
        );
    }

    if (error || !data) {
        return (
            <div style={{
                padding: '1.25rem 1.5rem',
                background: 'var(--neg-soft)',
                border: '1px solid var(--neg-line)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                color: 'var(--neg-bright)'
            }}>
                <div>
                    <div style={{ fontWeight: 800, fontSize: 'var(--fs-base)' }}>RELATIVE STRENGTH ENGINE OFFLINE</div>
                    <div style={{ fontSize: 'var(--fs-xs)', opacity: 0.8, marginTop: 4 }}>{error || 'No data available'}</div>
                </div>
                <button
                    onClick={fetchRSMatrix}
                    className="btn"
                    style={{ background: 'var(--neg-soft)', borderColor: 'var(--neg-line)', color: 'var(--neg-bright)' }}
                >
                    RETRY
                </button>
            </div>
        );
    }

    const { btc_regime, summary, candidates } = data;

    const filteredCandidates = candidates.filter((c) => {
        const matchesSearch = c.product_id.toLowerCase().includes(searchTerm.toLowerCase());
        if (!matchesSearch) return false;

        if (filterSignal === 'LONG') {
            return ['LONG_LEADER', 'OUTPERFORMER'].includes(c.rs_signal);
        }
        if (filterSignal === 'SHORT') {
            return ['SHORT_LAGGARD', 'DIVERGENT_SHORT', 'UNDERPERFORMER'].includes(c.rs_signal);
        }
        return true;
    });

    const getRegimeStyle = (regime: string) => {
        switch (regime) {
            case 'RISK_ON':
                return { bg: 'var(--pos-soft)', border: 'var(--pos-line)', color: 'var(--pos-bright)' };
            case 'RISK_OFF':
                return { bg: 'var(--neg-soft)', border: 'var(--neg-line)', color: 'var(--neg-bright)' };
            default:
                return { bg: 'var(--warn-soft)', border: 'var(--warn-line)', color: 'var(--warn-bright)' };
        }
    };

    const regStyle = getRegimeStyle(btc_regime.regime);

    const getSignalBadge = (signal: string) => {
        switch (signal) {
            case 'LONG_LEADER':
                return (
                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, padding: '0.15rem 0.5rem', background: 'var(--pos-soft)', color: 'var(--pos-bright)', border: '1px solid var(--pos-line)', fontSize: '0.68rem', fontWeight: 800, fontFamily: 'var(--font-mono)' }}>
                        <TrendingUp style={{ width: 12, height: 12 }} /> LONG LEADER
                    </span>
                );
            case 'OUTPERFORMER':
                return (
                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, padding: '0.15rem 0.5rem', background: 'var(--info-soft)', color: 'var(--info)', border: '1px solid var(--info-line)', fontSize: '0.68rem', fontWeight: 800, fontFamily: 'var(--font-mono)' }}>
                        <Zap style={{ width: 12, height: 12 }} /> OUTPERFORMER
                    </span>
                );
            case 'SHORT_LAGGARD':
                return (
                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, padding: '0.15rem 0.5rem', background: 'var(--neg-soft)', color: 'var(--neg-bright)', border: '1px solid var(--neg-line)', fontSize: '0.68rem', fontWeight: 800, fontFamily: 'var(--font-mono)' }}>
                        <TrendingDown style={{ width: 12, height: 12 }} /> SHORT LAGGARD
                    </span>
                );
            case 'DIVERGENT_SHORT':
                return (
                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, padding: '0.15rem 0.5rem', background: 'rgba(168, 85, 247, 0.15)', color: '#C084FC', border: '1px solid rgba(168, 85, 247, 0.35)', fontSize: '0.68rem', fontWeight: 800, fontFamily: 'var(--font-mono)' }}>
                        <ArrowDownRight style={{ width: 12, height: 12 }} /> SHORT DIVERGENCE
                    </span>
                );
            default:
                return (
                    <span style={{ display: 'inline-block', padding: '0.15rem 0.5rem', background: 'var(--surface-3)', color: 'var(--text-3)', border: '1px solid var(--line)', fontSize: '0.68rem', fontWeight: 700, fontFamily: 'var(--font-mono)' }}>
                        IN-LINE
                    </span>
                );
        }
    };

    return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
            {/* Top Banner Grid */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '1rem' }}>

                {/* Card 1: BTC Macro Regime */}
                <div style={{
                    background: regStyle.bg,
                    border: `1px solid ${regStyle.border}`,
                    padding: '1rem',
                    display: 'flex',
                    flexDirection: 'column',
                    justifyContent: 'space-between'
                }}>
                    <div>
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: '0.68rem', fontWeight: 800, letterSpacing: '0.06em', color: regStyle.color }}>
                                <Shield style={{ width: 14, height: 14 }} /> BTC MACRO REGIME
                            </div>
                            <span style={{
                                padding: '0.15rem 0.5rem',
                                fontSize: '0.68rem',
                                fontWeight: 800,
                                fontFamily: 'var(--font-mono)',
                                background: 'rgba(0,0,0,0.5)',
                                border: `1px solid ${regStyle.border}`,
                                color: regStyle.color
                            }}>
                                {btc_regime.regime} ({btc_regime.score > 0 ? `+${btc_regime.score}` : btc_regime.score})
                            </span>
                        </div>
                        <p style={{ fontSize: 'var(--fs-xs)', color: 'var(--text-2)', lineHeight: 1.4 }}>{btc_regime.reason}</p>
                    </div>

                    <div style={{
                        display: 'grid',
                        gridTemplateColumns: '1fr 1fr',
                        gap: '0.5rem',
                        marginTop: '0.75rem',
                        paddingTop: '0.5rem',
                        borderTop: `1px solid ${regStyle.border}`
                    }}>
                        <div>
                            <span style={{ fontSize: 'var(--fs-micro)', color: 'var(--text-4)', display: 'block', textTransform: 'uppercase' }}>NET DEALER GEX</span>
                            <span style={{ fontSize: 'var(--fs-sm)', fontWeight: 800, fontFamily: 'var(--font-mono)', color: 'var(--text-1)' }}>
                                ${(btc_regime.net_gex_millions / 1000).toFixed(2)}B
                            </span>
                        </div>
                        <div>
                            <span style={{ fontSize: 'var(--fs-micro)', color: 'var(--text-4)', display: 'block', textTransform: 'uppercase' }}>GAMMA FLIP DIST</span>
                            <span style={{ fontSize: 'var(--fs-sm)', fontWeight: 800, fontFamily: 'var(--font-mono)', color: 'var(--text-1)' }}>
                                {btc_regime.gamma_flip_dist_pct > 0 ? `+${btc_regime.gamma_flip_dist_pct}%` : `${btc_regime.gamma_flip_dist_pct}%`}
                            </span>
                        </div>
                    </div>
                </div>

                {/* Card 2: Universe RS Alpha Summary */}
                <div style={{
                    background: 'var(--surface-1)',
                    border: '1px solid var(--line)',
                    padding: '1rem',
                    display: 'flex',
                    flexDirection: 'column',
                    justifyContent: 'space-between'
                }}>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                        <span style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: '0.68rem', fontWeight: 800, color: 'var(--text-2)', letterSpacing: '0.06em' }}>
                            <Layers style={{ width: 14, height: 14, color: 'var(--info)' }} /> RS OPPORTUNITY MATRIX
                        </span>
                        <span style={{ fontSize: '0.68rem', fontFamily: 'var(--font-mono)', color: 'var(--text-4)' }}>
                            {summary.total_universe} Pairs Scanned
                        </span>
                    </div>

                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem', margin: '0.75rem 0' }}>
                        <div style={{ padding: '0.5rem 0.75rem', background: 'var(--pos-soft)', border: '1px solid var(--pos-line)' }}>
                            <span style={{ fontSize: 'var(--fs-micro)', fontWeight: 800, color: 'var(--pos-bright)', display: 'block' }}>LONG LEADERS</span>
                            <span style={{ fontSize: '1.4rem', fontWeight: 800, fontFamily: 'var(--font-mono)', color: 'var(--pos-bright)' }}>{summary.long_leaders_count}</span>
                        </div>
                        <div style={{ padding: '0.5rem 0.75rem', background: 'var(--neg-soft)', border: '1px solid var(--neg-line)' }}>
                            <span style={{ fontSize: 'var(--fs-micro)', fontWeight: 800, color: 'var(--neg-bright)', display: 'block' }}>SHORT LAGGARDS</span>
                            <span style={{ fontSize: '1.4rem', fontWeight: 800, fontFamily: 'var(--font-mono)', color: 'var(--neg-bright)' }}>{summary.short_laggards_count}</span>
                        </div>
                    </div>

                    <div style={{ fontSize: 'var(--fs-micro)', color: 'var(--text-4)' }}>
                        *Filters high beta alts on BTC Risk-On & weak alts on divergence.
                    </div>
                </div>

                {/* Card 3: Filters & Search */}
                <div style={{
                    background: 'var(--surface-1)',
                    border: '1px solid var(--line)',
                    padding: '1rem',
                    display: 'flex',
                    flexDirection: 'column',
                    justifyContent: 'space-between',
                    gap: '0.75rem'
                }}>
                    <span style={{ fontSize: '0.68rem', fontWeight: 800, color: 'var(--text-2)', letterSpacing: '0.06em' }}>SIGNAL FILTERS</span>

                    <div className="filter-tabs" style={{ width: '100%' }}>
                        <button
                            onClick={() => setFilterSignal('ALL')}
                            className={`tab-btn ${filterSignal === 'ALL' ? 'active' : ''}`}
                            style={{ flex: 1, textAlign: 'center' }}
                        >
                            ALL ({candidates.length})
                        </button>
                        <button
                            onClick={() => setFilterSignal('LONG')}
                            className={`tab-btn ${filterSignal === 'LONG' ? 'active' : ''}`}
                            style={{ flex: 1, textAlign: 'center' }}
                        >
                            LONG ({summary.long_leaders_count})
                        </button>
                        <button
                            onClick={() => setFilterSignal('SHORT')}
                            className={`tab-btn ${filterSignal === 'SHORT' ? 'active' : ''}`}
                            style={{ flex: 1, textAlign: 'center' }}
                        >
                            SHORT ({summary.short_laggards_count})
                        </button>
                    </div>

                    <div style={{ position: 'relative' }}>
                        <Search style={{ width: 14, height: 14, position: 'absolute', left: 10, top: 10, color: 'var(--text-4)' }} />
                        <input
                            type="text"
                            placeholder="Search symbol (e.g. SOL, ETH)..."
                            value={searchTerm}
                            onChange={(e) => setSearchTerm(e.target.value)}
                            style={{
                                width: '100%',
                                background: 'var(--surface-3)',
                                border: '1px solid var(--line)',
                                padding: '0.4rem 0.5rem 0.4rem 2rem',
                                fontSize: 'var(--fs-xs)',
                                color: 'var(--text-1)',
                                fontFamily: 'var(--font-mono)',
                                outline: 'none'
                            }}
                        />
                    </div>
                </div>

            </div>

            {/* Main Scanner Table */}
            <div className="scanner-table-container">
                <table className="scanner-table">
                    <thead>
                        <tr>
                            <th>SYMBOL</th>
                            <th>LAST PRICE</th>
                            <th>24H (USD)</th>
                            <th>RS (7D/30D BTC)</th>
                            <th>RS Z-SCORE</th>
                            <th>SIGNAL CLASSIFICATION</th>
                            <th style={{ textAlign: 'right' }}>ACTION</th>
                        </tr>
                    </thead>
                    <tbody>
                        {filteredCandidates.map((cand) => {
                            const zScore = cand.rs_z_score || 0;
                            const isPositive = zScore >= 0;
                            const absZ = Math.min(Math.abs(zScore) * 15, 100);

                            return (
                                <tr
                                    key={cand.product_id}
                                    onClick={() => onSelectSymbol && onSelectSymbol(cand.product_id)}
                                >
                                    <td style={{ fontWeight: 800, color: 'var(--text-1)', fontFamily: 'var(--font-mono)' }}>
                                        {cand.product_id}
                                    </td>
                                    <td className="mono" style={{ color: 'var(--text-2)' }}>
                                        ${cand.last_price?.toLocaleString()}
                                    </td>
                                    <td className="mono" style={{ fontWeight: 700, color: cand.day_change_pct >= 0 ? 'var(--pos-bright)' : 'var(--neg-bright)' }}>
                                        {cand.day_change_pct >= 0 ? `+${cand.day_change_pct?.toFixed(2)}%` : `${cand.day_change_pct?.toFixed(2)}%`}
                                    </td>
                                    <td className="mono" style={{ color: cand.rs_raw >= 0 ? 'var(--info)' : '#C084FC' }}>
                                        {cand.rs_raw >= 0 ? `+${cand.rs_raw?.toFixed(2)}%` : `${cand.rs_raw?.toFixed(2)}%`}
                                    </td>
                                    <td className="mono">
                                        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                                            <span style={{ width: 45, textAlign: 'right', fontWeight: 800, color: isPositive ? 'var(--pos-bright)' : 'var(--neg-bright)' }}>
                                                {isPositive ? `+${zScore.toFixed(2)}` : zScore.toFixed(2)}
                                            </span>
                                            <div className="pir-bar-bg" style={{ width: 70 }}>
                                                <div
                                                    className="pir-bar-fill"
                                                    style={{
                                                        width: `${absZ}%`,
                                                        background: isPositive ? 'var(--pos-bright)' : 'var(--neg-bright)'
                                                    }}
                                                />
                                            </div>
                                        </div>
                                    </td>
                                    <td>{getSignalBadge(cand.rs_signal)}</td>
                                    <td style={{ textAlign: 'right' }}>
                                        <button
                                            onClick={(e) => {
                                                e.stopPropagation();
                                                onSelectSymbol && onSelectSymbol(cand.product_id);
                                            }}
                                            className="btn"
                                            style={{ fontSize: '0.68rem', padding: '0.2rem 0.6rem' }}
                                        >
                                            SETUP LADDER
                                        </button>
                                    </td>
                                </tr>
                            );
                        })}
                    </tbody>
                </table>
            </div>
        </div>
    );
};
