from __future__ import annotations

import random
import statistics
from dataclasses import dataclass


@dataclass
class MonteCarloReport:
    simulations: int = 0
    initial_capital: float = 0.0
    horizon_days: int = 0
    final_equities: list[float] = None

    median_final: float = 0.0
    mean_final: float = 0.0
    p5_final: float = 0.0
    p95_final: float = 0.0
    worst_final: float = 0.0
    best_final: float = 0.0

    expected_return_pct: float = 0.0
    var_95_pct: float = 0.0
    cvar_95_pct: float = 0.0
    max_drawdown_median: float = 0.0
    prob_profit: float = 0.0
    prob_dd_over_10: float = 0.0
    prob_dd_over_20: float = 0.0

    def summary(self) -> dict:
        return {
            "simulations": self.simulations,
            "horizon_days": self.horizon_days,
            "median_final": round(self.median_final, 2),
            "mean_final": round(self.mean_final, 2),
            "p5_final": round(self.p5_final, 2),
            "p95_final": round(self.p95_final, 2),
            "worst_final": round(self.worst_final, 2),
            "best_final": round(self.best_final, 2),
            "expected_return_pct": round(self.expected_return_pct, 2),
            "var_95_pct": round(self.var_95_pct, 2),
            "cvar_95_pct": round(self.cvar_95_pct, 2),
            "max_drawdown_median_pct": round(self.max_drawdown_median * 100, 2),
            "prob_profit_pct": round(self.prob_profit * 100, 2),
            "prob_dd_over_10_pct": round(self.prob_dd_over_10 * 100, 2),
            "prob_dd_over_20_pct": round(self.prob_dd_over_20 * 100, 2),
        }


def _historical_returns_from_equity(equity_curve: list[dict]) -> list[float]:
    values = [p["equity"] for p in equity_curve if p.get("equity")]
    if len(values) < 2:
        return []
    return [(values[i] - values[i - 1]) / values[i - 1] for i in range(1, len(values))]


def _simulate_one_path(returns: list[float], initial: float, days: int) -> tuple[float, float]:
    if not returns:
        return initial, 0.0

    equity = initial
    peak = initial
    max_dd = 0.0
    for _ in range(days):
        r = random.choice(returns)
        equity *= 1 + r
        peak = max(peak, equity)
        dd = (peak - equity) / peak if peak else 0
        max_dd = max(max_dd, dd)
    return equity, max_dd


def run_monte_carlo(
    historical_returns: list[float],
    initial_capital: float = 100_000.0,
    horizon_days: int = 252,
    simulations: int = 1000,
    seed: int | None = 42,
) -> MonteCarloReport:
    if seed is not None:
        random.seed(seed)

    report = MonteCarloReport()
    report.simulations = simulations
    report.initial_capital = initial_capital
    report.horizon_days = horizon_days

    if not historical_returns:
        report.final_equities = [initial_capital] * simulations
        report.median_final = initial_capital
        report.mean_final = initial_capital
        return report

    final_equities: list[float] = []
    max_drawdowns: list[float] = []

    for _ in range(simulations):
        final_eq, max_dd = _simulate_one_path(historical_returns, initial_capital, horizon_days)
        final_equities.append(final_eq)
        max_drawdowns.append(max_dd)

    final_equities.sort()
    max_drawdowns.sort()

    report.final_equities = final_equities
    report.median_final = final_equities[simulations // 2]
    report.mean_final = statistics.mean(final_equities)
    report.p5_final = final_equities[int(simulations * 0.05)]
    report.p95_final = final_equities[int(simulations * 0.95)]
    report.worst_final = final_equities[0]
    report.best_final = final_equities[-1]

    report.expected_return_pct = (report.mean_final - initial_capital) / initial_capital * 100
    report.var_95_pct = (report.p5_final - initial_capital) / initial_capital * 100

    tail = final_equities[: int(simulations * 0.05)]
    if tail:
        cvar_dollar = statistics.mean(tail)
        report.cvar_95_pct = (cvar_dollar - initial_capital) / initial_capital * 100

    report.max_drawdown_median = max_drawdowns[simulations // 2]
    report.prob_profit = sum(1 for e in final_equities if e > initial_capital) / simulations
    report.prob_dd_over_10 = sum(1 for d in max_drawdowns if d > 0.10) / simulations
    report.prob_dd_over_20 = sum(1 for d in max_drawdowns if d > 0.20) / simulations

    return report


def run_from_backtest_result(
    equity_curve: list[dict],
    initial_capital: float = 100_000.0,
    horizon_days: int = 252,
    simulations: int = 1000,
) -> MonteCarloReport:
    returns = _historical_returns_from_equity(equity_curve)
    return run_monte_carlo(returns, initial_capital, horizon_days, simulations)


def kelly_fraction(win_rate: float, avg_win: float, avg_loss: float) -> float:
    if avg_loss == 0 or win_rate <= 0 or avg_win <= 0:
        return 0.0
    loss_abs = abs(avg_loss)
    b = avg_win / loss_abs
    p = win_rate
    q = 1 - p
    f = (b * p - q) / b
    return max(0.0, min(0.25, f))
