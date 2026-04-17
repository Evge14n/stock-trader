from __future__ import annotations

from dataclasses import dataclass, field

import structlog

from agents.python.backtest import run_backtest
from agents.python.data_collector import fetch_candles
from agents.python.indicators import _to_df
from agents.python.rl.env import EnvConfig, TradingEnv

log = structlog.get_logger(__name__)


@dataclass
class StrategyResult:
    name: str = ""
    total_pnl: float = 0.0
    total_pnl_pct: float = 0.0
    trades: int = 0
    wins: int = 0
    win_rate: float = 0.0
    final_capital: float = 0.0
    initial_capital: float = 0.0

    def summary(self) -> dict:
        return {
            "name": self.name,
            "total_pnl": round(self.total_pnl, 2),
            "total_pnl_pct": round(self.total_pnl_pct, 2),
            "trades": self.trades,
            "wins": self.wins,
            "win_rate": round(self.win_rate * 100, 2),
            "final_capital": round(self.final_capital, 2),
        }


@dataclass
class ABReport:
    symbols: list[str] = field(default_factory=list)
    period: str = ""
    rl: StrategyResult = field(default_factory=StrategyResult)
    bb: StrategyResult = field(default_factory=StrategyResult)
    winner: str = ""

    def summary(self) -> dict:
        return {
            "symbols": self.symbols,
            "period": self.period,
            "winner": self.winner,
            "rl": self.rl.summary(),
            "bb": self.bb.summary(),
            "delta_pnl_pct": round(self.rl.total_pnl_pct - self.bb.total_pnl_pct, 2),
        }


def _evaluate_rl(symbols: list[str], period: str, train_ratio: float, timesteps: int, initial: float) -> StrategyResult:
    from stable_baselines3 import PPO

    from agents.python.rl.trainer import build_vec_env

    result = StrategyResult(name="rl_ppo", initial_capital=initial)
    train_data: dict = {}
    test_data: dict = {}

    for sym in symbols:
        candles = fetch_candles(sym, period=period)
        if len(candles) < 80:
            continue
        df = _to_df(candles)
        split = int(len(df) * train_ratio)
        train_data[sym] = df.iloc[:split].reset_index(drop=True)
        test_data[sym] = df.iloc[split:].reset_index(drop=True)

    if not train_data or not test_data:
        result.final_capital = initial
        return result

    vec_env = build_vec_env(train_data)
    model = PPO(
        "MlpPolicy",
        vec_env,
        learning_rate=3e-4,
        n_steps=256,
        batch_size=64,
        gamma=0.99,
        seed=42,
        verbose=0,
    )
    log.info("ab_rl_train_start", symbols=list(train_data.keys()), timesteps=timesteps)
    model.learn(total_timesteps=timesteps, progress_bar=False)

    per_symbol_initial = initial / max(len(test_data), 1)
    for _sym, df in test_data.items():
        if len(df) < 40:
            continue
        env = TradingEnv(df, EnvConfig(initial_cash=per_symbol_initial, start_idx=30))
        obs, _ = env.reset(seed=0)
        done = False
        while not done:
            action, _ = model.predict(obs, deterministic=True)
            obs, _, done, _, _ = env.step(int(action))
        s = env.summary()
        result.trades += s["trades"]
        result.wins += s["wins"]
        result.total_pnl += s["total_pnl"]
        result.final_capital += s["final_equity"]

    result.win_rate = result.wins / result.trades if result.trades else 0.0
    result.total_pnl_pct = (result.total_pnl / initial * 100) if initial else 0.0
    return result


def _evaluate_bb(symbols: list[str], period: str, train_ratio: float, initial: float) -> StrategyResult:
    result = StrategyResult(name="bb_mean_reversion", initial_capital=initial)

    bt = run_backtest(symbols, initial_capital=initial, period=period)

    if not bt.equity_curve:
        result.final_capital = initial
        return result

    split = int(len(bt.equity_curve) * train_ratio)
    split_ts = bt.equity_curve[split]["timestamp"] if split < len(bt.equity_curve) else None

    test_trades = [t for t in bt.trades if split_ts and t.get("closed_at", "") >= split_ts]
    test_pnl = sum(t["pnl"] for t in test_trades)
    wins = sum(1 for t in test_trades if t["pnl"] > 0)

    result.trades = len(test_trades)
    result.wins = wins
    result.win_rate = wins / result.trades if result.trades else 0.0
    result.total_pnl = test_pnl
    result.total_pnl_pct = (test_pnl / initial * 100) if initial else 0.0
    result.final_capital = initial + test_pnl
    return result


def run_ab(
    symbols: list[str],
    period: str = "2y",
    train_ratio: float = 0.7,
    timesteps: int = 50_000,
    initial: float = 100_000.0,
) -> ABReport:
    report = ABReport(symbols=list(symbols), period=period)
    report.rl = _evaluate_rl(symbols, period, train_ratio, timesteps, initial)
    report.bb = _evaluate_bb(symbols, period, train_ratio, initial)

    if report.rl.total_pnl > report.bb.total_pnl:
        report.winner = "rl_ppo"
    elif report.bb.total_pnl > report.rl.total_pnl:
        report.winner = "bb_mean_reversion"
    else:
        report.winner = "tie"
    return report
