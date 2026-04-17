from __future__ import annotations

from dataclasses import dataclass, field
from itertools import product

from agents.python.backtest import run_backtest


@dataclass
class ParamResult:
    stop_loss_pct: float = 0.0
    take_profit_pct: float = 0.0
    risk_per_trade: float = 0.0
    total_pnl: float = 0.0
    total_pnl_pct: float = 0.0
    win_rate: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown: float = 0.0
    total_trades: int = 0

    def score(self) -> float:
        if self.max_drawdown == 0:
            return self.total_pnl_pct
        return self.total_pnl_pct / max(self.max_drawdown, 1)


@dataclass
class OptimizerReport:
    best: ParamResult | None = None
    all_results: list[ParamResult] = field(default_factory=list)
    param_space_size: int = 0

    def top_n(self, n: int = 10) -> list[ParamResult]:
        return sorted(self.all_results, key=lambda r: r.score(), reverse=True)[:n]


def run_grid_search(
    symbols: list[str],
    period: str = "1y",
    initial_capital: float = 100_000.0,
    sl_values: list[float] | None = None,
    tp_values: list[float] | None = None,
    risk_values: list[float] | None = None,
) -> OptimizerReport:
    sl_values = sl_values or [0.02, 0.03, 0.04, 0.05]
    tp_values = tp_values or [0.04, 0.06, 0.08, 0.10, 0.12]
    risk_values = risk_values or [0.01, 0.02, 0.03]

    report = OptimizerReport()
    combinations = list(product(sl_values, tp_values, risk_values))
    report.param_space_size = len(combinations)

    best_score = float("-inf")

    for sl, tp, risk in combinations:
        if tp <= sl:
            continue

        result = run_backtest(
            symbols=symbols,
            initial_capital=initial_capital,
            period=period,
            risk_per_trade=risk,
            stop_loss_pct=sl,
            take_profit_pct=tp,
        )
        summary = result.summary()

        pr = ParamResult(
            stop_loss_pct=sl,
            take_profit_pct=tp,
            risk_per_trade=risk,
            total_pnl=summary["total_pnl"],
            total_pnl_pct=summary["total_pnl_pct"],
            win_rate=summary["win_rate"],
            sharpe_ratio=summary["sharpe_ratio"],
            max_drawdown=summary["max_drawdown"],
            total_trades=summary["total_trades"],
        )
        report.all_results.append(pr)

        score = pr.score()
        if score > best_score:
            best_score = score
            report.best = pr

    return report
