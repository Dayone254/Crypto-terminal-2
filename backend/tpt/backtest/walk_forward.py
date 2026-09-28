"""Walk-forward validation engine — rolling window evaluation and candidate ranking.

Methodology notes (fixes applied):
- Granularity honesty: the loader used to fetch only 900s candles and hand them
  to the evaluator as "1h" bars (stepping [::12] called them 12h). Every "1h"
  indicator in every historical result was therefore computed on 15-minute data.
  Windows are now driven by true 1h bars by default; a 15m dataset is loaded
  separately as context and sliced strictly to the evaluation timestamp.
- Zero look-ahead in auxiliary slices: the 15m slice is cut at the last bar
  whose close time is <= the evaluation bar's close. Daily slices are only used
  when a daily archive exists, and only up to the last *closed* daily bar.
- Train → test coupling: threshold-only candidates are no longer decorative.
  Each window's train span is replayed, the EV-maximising minimum score is
  estimated from those train trades, and the test span is evaluated under that
  calibrated threshold. The train window always precedes the test window, so
  the calibration sees no future data.
"""
from __future__ import annotations

import copy
import logging
from dataclasses import asdict, dataclass, field
from typing import Any

from tpt.backtest.engine import BacktestTradeResult, evaluate_bar_slice, simulate_trade_execution
from tpt.backtest.storage import SURVIVORSHIP_BIAS_NOTE, load_historical_candles_sync
from tpt.config.strategy import StrategyConfig, load_strategy

logger = logging.getLogger(__name__)

_VALID_GRANULARITY = (60, 900, 3600, 21600, 86400)


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


def _calibrate_min_score(
    train_rows: list[dict[str, Any]],
    fallback: float,
    *,
    min_cohort: int = 20,
    min_train_trades: int = 40,
) -> float | None:
    """EV-maximising minimum score from train-window trades, or None.

    Refuses to answer below ``min_train_trades`` closed train trades — with
    fewer, the "optimal" threshold is noise. The answer is clamped into
    ``[max(45, fallback-10), fallback+15]`` so the calibration sharpens a
    candidate's own identity instead of wandering into an untested regime.
    """
    if len(train_rows) < min_train_trades:
        return None

    best_ev: float | None = None
    best_thr: float | None = None
    for thr in sorted({round(float(r["score"])) for r in train_rows}):
        cohort = [r for r in train_rows if float(r["score"]) >= thr]
        if len(cohort) < min_cohort:
            continue
        ev = sum(float(r["realized_r"]) for r in cohort) / len(cohort)
        if best_ev is None or ev > best_ev:
            best_ev = ev
            best_thr = float(thr)

    if best_thr is None:
        return None

    lo = max(45.0, fallback - 10.0)
    hi = fallback + 15.0
    return round(min(max(best_thr, lo), hi), 1)


from tpt.strategies.base import BaseStrategy
from tpt.strategies.registry import get_all_strategies, get_strategy_by_id


def run_walk_forward_backtest(
    symbols: list[str],
    candidates: list[StrategyCandidateConfig] | None = None,
    strategies: list[BaseStrategy] | None = None,
    granularity: int = 3600,
    train_days: int = 365,
    test_days: int = 90,
    step_days: int = 90,
) -> list[WalkForwardCandidateResult]:
    """Execute walk-forward validation across candidate strategy parameter sets or strategy plugins.

    ``granularity`` is the primary evaluation bar size in seconds and defaults to
    3600 (true 1h). When the primary bar is hourly or larger, a 15m dataset is
    loaded as auxiliary context for the multi-timeframe features — sliced to the
    evaluation timestamp so nothing from the future leaks in.
    """
    if not candidates and not strategies:
        # Load default parameter candidates AND pluggable strategies
        candidates = [
            StrategyCandidateConfig(name="Default v2.0 (Score >= 60)", min_composite_score=60.0),
            StrategyCandidateConfig(name="Conservative (Score >= 70)", min_composite_score=70.0),
            StrategyCandidateConfig(name="Aggressive (Score >= 55)", min_composite_score=55.0),
            StrategyCandidateConfig(name="High Volume Floor ($2M+)", min_composite_score=60.0, min_quote_volume=2_000_000.0),
        ]
        strategies = get_all_strategies()

    gran = granularity if granularity in _VALID_GRANULARITY else 3600
    # 15m context only makes sense when the primary bars are hourly or larger;
    # on a 15m primary there is no finer archive to add.
    aux_granularity = 900 if gran >= 3600 else None

    candles_by_symbol: dict[str, list[list[Any]]] = {}
    aux_by_symbol: dict[str, list[list[Any]]] = {}
    min_ts: int = 2**63 - 1
    max_ts: int = 0

    for s in symbols:
        c_list = load_historical_candles_sync(s, granularity=gran)
        if c_list and len(c_list) > 50:
            candles_by_symbol[s] = c_list
            min_ts = min(min_ts, int(c_list[0][0]))
            max_ts = max(max_ts, int(c_list[-1][0]))
        if aux_granularity:
            a_list = load_historical_candles_sync(s, granularity=aux_granularity)
            if a_list and len(a_list) > 50:
                aux_by_symbol[s] = a_list

    if not candles_by_symbol or min_ts == 2**63 - 1:
        logger.warning(
            "No historical %ds candle data found for walk-forward validation — "
            "run /api/v1/research/expand-history first.",
            gran,
        )
        return []

    windows = generate_rolling_windows(min_ts, max_ts, train_days, test_days, step_days)
    logger.info(
        "Generated %d walk-forward windows for %d symbols (primary %ds bars, %s)",
        len(windows), len(candles_by_symbol), gran,
        "15m context" if aux_by_symbol else "no 15m context available",
    )

    btc_candles = candles_by_symbol.get("BTC-USD")
    btc_aux = aux_by_symbol.get("BTC-USD")

    # Index timestamp -> position once per dataset; slices are then cut at the
    # last bar closing at or before the evaluation timestamp.
    def _index(candles: list[list[Any]]) -> dict[int, int]:
        return {int(c[0]): i for i, c in enumerate(candles)}

    btc_index = _index(btc_candles) if btc_candles else {}
    btc_aux_index = _index(btc_aux) if btc_aux else {}
    per_symbol_index = {s: _index(c) for s, c in candles_by_symbol.items()}
    per_symbol_aux_index = {s: _index(a) for s, a in aux_by_symbol.items()}

    def _build_slicer(candles: list[list[Any]]):
        opens = [int(c[0]) for c in candles]

        def slice_to(ts: int) -> list[list[Any]] | None:
            import bisect
            # Last bar that CLOSED at or before ts: open + gran <= ts.
            j = bisect.bisect_right(opens, ts - gran) - 1
            if j < 0:
                return None
            return candles[: j + 1]

        return slice_to

    slice_primary = {s: _build_slicer(c) for s, c in candles_by_symbol.items()}
    slice_aux = {s: _build_slicer(a) for s, a in aux_by_symbol.items()}
    slice_btc = _build_slicer(btc_candles) if btc_candles else None
    slice_btc_aux = _build_slicer(btc_aux) if btc_aux else None

    def _replay_range(
        start_ts: int,
        end_ts: int,
        cfg: StrategyConfig,
        st_inst: BaseStrategy | None,
    ) -> tuple[list[BacktestTradeResult], list[dict[str, Any]]]:
        """Replay [start_ts, end_ts] under cfg, trades resolved on bars clipped to end_ts."""
        trades: list[BacktestTradeResult] = []
        rows: list[dict[str, Any]] = []

        for sym, candles in candles_by_symbol.items():
            index = per_symbol_index[sym]
            test_indices = [
                i for i, c in enumerate(candles)
                if start_ts <= int(c[0]) <= end_ts and i >= 30
            ]
            aux_slice = slice_aux.get(sym)

            for i in test_indices[::12]:
                ts = int(candles[i][0])
                candle_slice = candles[: i + 1]

                btc_slice = slice_btc(ts) if slice_btc else None
                candles_15m_slice = aux_slice(ts) if aux_slice else None

                setup = evaluate_bar_slice(
                    symbol=sym,
                    candles_1h_slice=candle_slice,
                    candles_1d_slice=None,
                    candles_15m_slice=candles_15m_slice,
                    candles_6h_slice=None,
                    btc_1h_slice=btc_slice,
                    btc_1d_slice=None,
                    config=cfg,
                    strategy=st_inst,
                )

                if setup and setup["label"] in ("ENTRY_ZONE", "COILED"):
                    # Futures clipped to the window end: a train-window
                    # calibration trade must not borrow outcomes from the test
                    # period (or beyond the dataset).
                    future_bars = [c for c in candles[i + 1:] if int(c[0]) <= end_ts]
                    if future_bars:
                        trade = simulate_trade_execution(setup, future_bars)
                        if trade:
                            trades.append(trade)
                            rows.append({
                                "score": float(setup["score"]),
                                "status": trade.status,
                                "realized_r": float(trade.realized_r),
                            })

        return trades, rows

    # Build combined evaluation list: (candidate_config, strategy_instance)
    eval_list: list[tuple[StrategyCandidateConfig, BaseStrategy | None]] = []
    if candidates:
        for c in candidates:
            eval_list.append((c, None))
    if strategies:
        for st in strategies:
            cfg = StrategyCandidateConfig(name=st.name)
            eval_list.append((cfg, st))

    results: list[WalkForwardCandidateResult] = []

    for cand, st_inst in eval_list:
        base_cfg = copy.deepcopy(load_strategy())
        # Override candidate parameters if evaluating standard candidate
        if st_inst is None:
            base_cfg.labeling.min_composite_score = cand.min_composite_score
            base_cfg.labeling.min_quote_volume = cand.min_quote_volume
            base_cfg.ladder.atr_stop_mult = cand.atr_stop_mult

        window_perfs: list[WindowPerformance] = []
        all_trades: list[BacktestTradeResult] = []

        for idx, (tr_s, tr_e, te_s, te_e) in enumerate(windows):
            # ── TRAIN: replay the training span under the candidate's base config ──
            _train_trades, train_rows = _replay_range(tr_s, tr_e, base_cfg, st_inst)

            # ── CALIBRATE: threshold-only candidates earn their test config ──
            test_cfg = base_cfg
            calibrated_from = None
            if st_inst is None:
                thr = _calibrate_min_score(train_rows, cand.min_composite_score)
                if thr is not None:
                    test_cfg = copy.deepcopy(base_cfg)
                    test_cfg.labeling.min_composite_score = thr
                    calibrated_from = thr

            # ── TEST: evaluate the held-out span under the calibrated config ──
            window_trades, _ = _replay_range(te_s, te_e, test_cfg, st_inst)

            if calibrated_from is not None:
                logger.debug(
                    "Candidate %s window %d: calibrated min score %.1f -> %.1f (%d train trades)",
                    cand.name, idx, cand.min_composite_score, calibrated_from, len(train_rows),
                )

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
