from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from agents.python.backtest import BacktestResult, run_backtest
from agents.python.data_collector import fetch_candles


@dataclass
class WalkForwardWindow:
    train_start: str = ""
    train_end: str = ""
    test_start: str = ""
    test_end: str = ""
    train_result: dict = field(default_factory=dict)
    test_result: dict = field(default_factory=dict)


@dataclass
class WalkForwardReport:
    windows: list[WalkForwardWindow] = field(default_factory=list)
    combined_test_pnl: float = 0.0
    combined_test_pnl_pct: float = 0.0
    avg_sharpe: float = 0.0
    avg_win_rate: float = 0.0
    consistency: float = 0.0

    def summary(self) -> dict:
        return {
            "windows": len(self.windows),
            "combined_test_pnl": round(self.combined_test_pnl, 2),
            "combined_test_pnl_pct": round(self.combined_test_pnl_pct, 2),
            "avg_sharpe": round(self.avg_sharpe, 3),
            "avg_win_rate": round(self.avg_win_rate * 100, 2),
            "consistency_pct": round(self.consistency * 100, 2),
        }


def _load_per_symbol(symbols: list[str], period: str) -> dict[str, list[dict]]:
    data = {}
    for sym in symbols:
        candles = fetch_candles(sym, period=period)
        if candles:
            data[sym] = candles
    return data


def _split_windows(
    data: dict[str, list[dict]],
    train_days: int,
    test_days: int,
    step_days: int,
) -> list[tuple[int, int, int, int]]:
    if not data:
        return []

    all_ts = set()
    for candles in data.values():
        for c in candles:
            all_ts.add(c["timestamp"])
    sorted_ts = sorted(all_ts)

    if len(sorted_ts) < train_days + test_days:
        return []

    windows = []
    step = max(step_days, 1)
    for i in range(0, len(sorted_ts) - train_days - test_days + 1, step):
        windows.append(
            (
                sorted_ts[i],
                sorted_ts[i + train_days - 1],
                sorted_ts[i + train_days],
                sorted_ts[min(i + train_days + test_days - 1, len(sorted_ts) - 1)],
            )
        )
    return windows


def _filter_candles(candles: list[dict], start_ts: int, end_ts: int) -> list[dict]:
    return [c for c in candles if start_ts <= c["timestamp"] <= end_ts]


def _run_window_backtest(
    data: dict[str, list[dict]],
    start_ts: int,
    end_ts: int,
    initial_capital: float,
) -> BacktestResult:
    from agents.python import backtest

    filtered = {sym: _filter_candles(c, start_ts, end_ts) for sym, c in data.items()}
    filtered = {sym: c for sym, c in filtered.items() if len(c) >= 30}

    if not filtered:
        r = BacktestResult()
        r.initial_capital = initial_capital
        r.final_capital = initial_capital
        return r

    original = backtest.fetch_candles

    def _mock_fetch(sym, period="6mo"):
        return filtered.get(sym, [])

    backtest.fetch_candles = _mock_fetch
    try:
        return run_backtest(list(filtered.keys()), initial_capital, period="6mo")
    finally:
        backtest.fetch_candles = original


def run_walk_forward(
    symbols: list[str],
    total_period: str = "2y",
    train_days: int = 90,
    test_days: int = 30,
    step_days: int = 30,
    initial_capital: float = 100_000.0,
) -> WalkForwardReport:
    report = WalkForwardReport()
    data = _load_per_symbol(symbols, total_period)
    if not data:
        return report

    windows = _split_windows(data, train_days, test_days, step_days)
    if not windows:
        return report

    test_pnls: list[float] = []
    sharpes: list[float] = []
    win_rates: list[float] = []

    for train_start, train_end, test_start, test_end in windows:
        w = WalkForwardWindow()
        w.train_start = datetime.fromtimestamp(train_start).strftime("%Y-%m-%d")
        w.train_end = datetime.fromtimestamp(train_end).strftime("%Y-%m-%d")
        w.test_start = datetime.fromtimestamp(test_start).strftime("%Y-%m-%d")
        w.test_end = datetime.fromtimestamp(test_end).strftime("%Y-%m-%d")

        train_res = _run_window_backtest(data, train_start, train_end, initial_capital)
        test_res = _run_window_backtest(data, test_start, test_end, initial_capital)

        w.train_result = train_res.summary()
        w.test_result = test_res.summary()
        report.windows.append(w)

        test_pnls.append(test_res.total_pnl)
        sharpes.append(test_res.sharpe_ratio)
        win_rates.append(test_res.win_rate)

    total_test_pnl = sum(test_pnls)
    combined_initial = initial_capital * len(test_pnls)
    report.combined_test_pnl = total_test_pnl
    report.combined_test_pnl_pct = (total_test_pnl / combined_initial * 100) if combined_initial else 0.0
    report.avg_sharpe = sum(sharpes) / len(sharpes) if sharpes else 0.0
    report.avg_win_rate = sum(win_rates) / len(win_rates) if win_rates else 0.0

    profitable_windows = sum(1 for p in test_pnls if p > 0)
    report.consistency = profitable_windows / len(test_pnls) if test_pnls else 0.0

    return report
