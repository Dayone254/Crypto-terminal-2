"""Walk-forward validation engine — rolling window evaluation and candidate ranking."""
from __future__ import annotations

import logging, math
from dataclasses import asdict, dataclass, field
from typing import Any

from tpt.backtest.engine import BacktestTradeResult, evaluate_bar_slice, simulate_trade_execution
from tpt.backtest.storage import SURVIVORSHIP_BIAS_NOTE, load_historical_candles_sync
from tpt.config.strategy import StrategyConfig, load_strategy

logger = logging.getLogger(__name__)


@dataclass
class StrategyCandidateConfig:
    name: str
    min_composite_score: float = 60.0
    min_quote_volume: float = 1_000_000.0
    atr_stop_mult: float = 1.5
    trend_veto_enabled: bool = True


@dataclass
class WindowPerformance:
    window_index: int
    train_start_ts: int
    train_end_ts: int
    test_start_ts: int
    test_end_ts: int
    trades_count: int
    win_rate: float
    avg_r: float
    max_drawdown_pct: float
    l2_approximated: bool = True
    trades: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class WalkForwardCandidateResult:
    candidate_name: str
    config: StrategyCandidateConfig
    overall_win_rate: float
    overall_avg_r: float
    overall_trades_count: int
    consistency_score: float  # Share of windows with positive expectancy
    window_results: list[WindowPerformance] = field(default_factory=list)
    l2_approximated: bool = True
    survivorship_bias_note: str = SURVIVORSHIP_BIAS_NOTE


def generate_rolling_windows(
    start_ts: int,
    end_ts: int,
    train_days: int = 365,
    test_days: int = 90,
    step_days: int = 90,
) -> list[tuple[int, int, int, int]]:
    """Generate sequential (train_start, train_end, test_start, test_end) windows."""
    day_sec = 86400
    train_span = train_days * day_sec
    test_span = test_days * day_sec
    step_span = step_days * day_sec

    windows = []
    curr_train_start = start_ts
    while True:
        curr_train_end = curr_train_start + train_span
        curr_test_start = curr_train_end
        curr_test_end = curr_test_start + test_span

        if curr_test_end > end_ts:
            if curr_test_start < end_ts:
                # Include truncated final window
                windows.append((curr_train_start, curr_train_end, curr_test_start, end_ts))
            break

        windows.append((curr_train_start, curr_train_end, curr_test_start, curr_test_end))
        curr_train_start += step_span

    return windows


from tpt.strategies.base import BaseStrategy
from tpt.strategies.registry import get_all_strategies, get_strategy_by_id

def run_walk_forward_backtest(
    symbols: list[str],
    candidates: list[StrategyCandidateConfig] | None = None,
    strategies: list[BaseStrategy] | None = None,
    granularity: int = 900,
    train_days: int = 365,
    test_days: int = 90,
    step_days: int = 90,
) -> list[WalkForwardCandidateResult]:
    """Execute walk-forward validation across candidate strategy parameter sets or strategy plugins."""
    if not candidates and not strategies:
        # Load default parameter candidates AND pluggable strategies
        candidates = [
            StrategyCandidateConfig(name="Default v2.0 (Score >= 60)", min_composite_score=60.0),
            StrategyCandidateConfig(name="Conservative (Score >= 70)", min_composite_score=70.0),
            StrategyCandidateConfig(name="Aggressive (Score >= 55)", min_composite_score=55.0),
            StrategyCandidateConfig(name="High Volume Floor ($2M+)", min_composite_score=60.0, min_quote_volume=2_000_000.0),
        ]
        strategies = get_all_strategies()

    # Load historical candles per symbol
    candles_by_symbol: dict[str, list[list[Any]]] = {}
    min_ts: int = 2**63 - 1
    max_ts: int = 0

    for s in symbols:
        c_list = load_historical_candles_sync(s, granularity=granularity)
        if c_list and len(c_list) > 50:
            candles_by_symbol[s] = c_list
            min_ts = min(min_ts, int(c_list[0][0]))
            max_ts = max(max_ts, int(c_list[-1][0]))

    if not candles_by_symbol or min_ts == 2**63 - 1:
        logger.warning("No historical candle data found for walk-forward validation.")
        return []

    windows = generate_rolling_windows(min_ts, max_ts, train_days, test_days, step_days)
    logger.info("Generated %d walk-forward windows for %d symbols", len(windows), len(candles_by_symbol))

    btc_candles = candles_by_symbol.get("BTC-USD")
    results: list[WalkForwardCandidateResult] = []

    # Build combined evaluation list: (candidate_config, strategy_instance)
    eval_list: list[tuple[StrategyCandidateConfig, BaseStrategy | None]] = []
    if candidates:
        for c in candidates:
            eval_list.append((c, None))
    if strategies:
        for st in strategies:
            cfg = StrategyCandidateConfig(name=st.name)
            eval_list.append((cfg, st))

    for cand, st_inst in eval_list:
        base_cfg = load_strategy()
        # Override candidate parameters if evaluating standard candidate
        if st_inst is None:
            base_cfg.labeling.min_composite_score = cand.min_composite_score
            base_cfg.labeling.min_quote_volume = cand.min_quote_volume
            base_cfg.ladder.atr_stop_mult = cand.atr_stop_mult

        window_perfs: list[WindowPerformance] = []
        all_trades: list[BacktestTradeResult] = []

        for idx, (tr_s, tr_e, te_s, te_e) in enumerate(windows):
            window_trades: list[BacktestTradeResult] = []

            for sym, candles in candles_by_symbol.items():
                # Filter test range indices
                test_indices = [
                    i for i, c in enumerate(candles)
                    if te_s <= c[0] <= te_e and i >= 30
                ]
                btc_indices = {c[0]: i for i, c in enumerate(btc_candles)} if btc_candles else {}

                for i in test_indices[::12]:  # Step every 12 hours for optimized walk-forward evaluation
                    candle_slice = candles[: i + 1]
                    ts = candles[i][0]

                    # Slice BTC candles up to same timestamp (no look-ahead)
                    btc_slice = None
                    if btc_candles and ts in btc_indices:
                        b_idx = btc_indices[ts]
                        btc_slice = btc_candles[: b_idx + 1]

                    setup = evaluate_bar_slice(
                        symbol=sym,
                        candles_1h_slice=candle_slice,
                        candles_15m_slice=candle_slice,
                        btc_1h_slice=btc_slice,
                        config=base_cfg,
                        strategy=st_inst,
                    )

                    if setup and setup["label"] in ("ENTRY_ZONE", "COILED"):
                        future_bars = candles[i + 1 :]
                        if future_bars:
                            trade = simulate_trade_execution(setup, future_bars)
                            if trade:
                                window_trades.append(trade)

            # Compute window metrics
            n_trades = len(window_trades)
            wins = sum(1 for t in window_trades if t.status in ("WIN", "PARTIAL_WIN"))
            win_rate = round(wins / n_trades * 100.0, 1) if n_trades > 0 else 0.0
            avg_r = round(sum(t.realized_r for t in window_trades) / n_trades, 2) if n_trades > 0 else 0.0

            # Calculate max drawdown in R
            cum_r = 0.0
            peak_r = 0.0
            max_dd = 0.0
            for t in window_trades:
                cum_r += t.realized_r
                if cum_r > peak_r:
                    peak_r = cum_r
                dd = peak_r - cum_r
                if dd > max_dd:
                    max_dd = dd

            w_perf = WindowPerformance(
                window_index=idx,
                train_start_ts=tr_s,
                train_end_ts=tr_e,
                test_start_ts=te_s,
                test_end_ts=te_e,
                trades_count=n_trades,
                win_rate=win_rate,
                avg_r=avg_r,
                max_drawdown_pct=round(max_dd, 2),
                l2_approximated=True,
                trades=[asdict(t) for t in window_trades],
            )
            window_perfs.append(w_perf)
            all_trades.extend(window_trades)

        tot_trades = len(all_trades)
        tot_wins = sum(1 for t in all_trades if t.status in ("WIN", "PARTIAL_WIN"))
        overall_wr = round(tot_wins / tot_trades * 100.0, 1) if tot_trades > 0 else 0.0
        overall_avg_r = round(sum(t.realized_r for t in all_trades) / tot_trades, 2) if tot_trades > 0 else 0.0
        
        # Consistency score: proportion of windows with avg_r > 0
        pos_windows = sum(1 for w in window_perfs if w.avg_r > 0 and w.trades_count >= 2)
        total_valid_windows = max(1, sum(1 for w in window_perfs if w.trades_count >= 2))
        consistency = round(pos_windows / total_valid_windows * 100.0, 1)

        cand_result = WalkForwardCandidateResult(
            candidate_name=cand.name,
            config=cand,
            overall_win_rate=overall_wr,
            overall_avg_r=overall_avg_r,
            overall_trades_count=tot_trades,
            consistency_score=consistency,
            window_results=window_perfs,
            l2_approximated=True,
            survivorship_bias_note=SURVIVORSHIP_BIAS_NOTE,
        )
        results.append(cand_result)

    # Rank candidate strategies by consistency score and overall avg R
    results.sort(key=lambda r: (r.consistency_score, r.overall_avg_r), reverse=True)
    return results
