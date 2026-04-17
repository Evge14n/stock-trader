from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd
import structlog

from agents.python.data_collector import fetch_candles
from agents.python.indicators import _to_df
from agents.python.rl.env import EnvConfig, TradingEnv

log = structlog.get_logger(__name__)


@dataclass
class RLWindow:
    train_start: str = ""
    train_end: str = ""
    test_start: str = ""
    test_end: str = ""
    train_bars: int = 0
    test_bars: int = 0
    test_result: dict = field(default_factory=dict)


@dataclass
class RLWalkForwardReport:
    windows: list[RLWindow] = field(default_factory=list)
    combined_test_pnl: float = 0.0
    combined_final_equity: float = 0.0
    avg_win_rate: float = 0.0
    consistency: float = 0.0
    symbols: list[str] = field(default_factory=list)

    def summary(self) -> dict:
        return {
            "windows": len(self.windows),
            "symbols": len(self.symbols),
            "combined_test_pnl": round(self.combined_test_pnl, 2),
            "combined_final_equity": round(self.combined_final_equity, 2),
            "avg_win_rate": round(self.avg_win_rate * 100, 2),
            "consistency_pct": round(self.consistency * 100, 2),
        }


def _load_per_symbol(symbols: list[str], period: str) -> dict[str, pd.DataFrame]:
    out: dict[str, pd.DataFrame] = {}
    for sym in symbols:
        candles = fetch_candles(sym, period=period)
        if not candles:
            continue
        df = _to_df(candles)
        if len(df) > 60:
            out[sym] = df
    return out


def _split_indices(n_bars: int, train_bars: int, test_bars: int, step: int) -> list[tuple[int, int, int, int]]:
    if n_bars < train_bars + test_bars:
        return []
    windows = []
    step = max(step, 1)
    for i in range(0, n_bars - train_bars - test_bars + 1, step):
        windows.append((i, i + train_bars, i + train_bars, min(i + train_bars + test_bars, n_bars)))
    return windows


def _train_on_slice(train_data: dict[str, pd.DataFrame], timesteps: int, seed: int):
    from stable_baselines3 import PPO

    from agents.python.rl.trainer import build_vec_env

    vec_env = build_vec_env(train_data)
    model = PPO(
        "MlpPolicy",
        vec_env,
        learning_rate=3e-4,
        n_steps=256,
        batch_size=64,
        gamma=0.99,
        seed=seed,
        verbose=0,
    )
    model.learn(total_timesteps=timesteps, progress_bar=False)
    return model


def _eval_on_slice(model, test_data: dict[str, pd.DataFrame]) -> dict[str, dict]:
    results: dict[str, dict] = {}
    for sym, df in test_data.items():
        if len(df) < 40:
            continue
        env = TradingEnv(df.reset_index(drop=True), EnvConfig(start_idx=30))
        obs, _ = env.reset(seed=0)
        done = False
        while not done:
            action, _ = model.predict(obs, deterministic=True)
            obs, _, done, _, _ = env.step(int(action))
        results[sym] = env.summary()
    return results


def run_rl_walk_forward(
    symbols: list[str],
    period: str = "2y",
    train_bars: int = 180,
    test_bars: int = 60,
    step_bars: int = 60,
    timesteps: int = 20_000,
    seed: int = 42,
) -> RLWalkForwardReport:
    report = RLWalkForwardReport(symbols=list(symbols))
    data = _load_per_symbol(symbols, period)
    if not data:
        log.warning("rl_walk_forward_no_data")
        return report

    min_bars = min(len(df) for df in data.values())
    windows = _split_indices(min_bars, train_bars, test_bars, step_bars)
    if not windows:
        log.warning("rl_walk_forward_no_windows", min_bars=min_bars)
        return report

    test_pnls: list[float] = []
    win_rates: list[float] = []
    final_equities: list[float] = []

    for idx, (ts0, ts1, te0, te1) in enumerate(windows):
        train_data = {sym: df.iloc[ts0:ts1].reset_index(drop=True) for sym, df in data.items()}
        test_data = {sym: df.iloc[te0:te1].reset_index(drop=True) for sym, df in data.items()}
        train_data = {s: d for s, d in train_data.items() if len(d) > 40}
        test_data = {s: d for s, d in test_data.items() if len(d) > 30}
        if not train_data or not test_data:
            continue

        log.info("rl_wf_window", idx=idx + 1, total=len(windows), train_bars=ts1 - ts0, test_bars=te1 - te0)

        model = _train_on_slice(train_data, timesteps=timesteps, seed=seed + idx)
        results = _eval_on_slice(model, test_data)

        w = RLWindow(
            train_start=datetime.fromtimestamp(int(next(iter(train_data.values())).iloc[0]["timestamp"])).strftime(
                "%Y-%m-%d"
            ),
            train_end=datetime.fromtimestamp(int(next(iter(train_data.values())).iloc[-1]["timestamp"])).strftime(
                "%Y-%m-%d"
            ),
            test_start=datetime.fromtimestamp(int(next(iter(test_data.values())).iloc[0]["timestamp"])).strftime(
                "%Y-%m-%d"
            ),
            test_end=datetime.fromtimestamp(int(next(iter(test_data.values())).iloc[-1]["timestamp"])).strftime(
                "%Y-%m-%d"
            ),
            train_bars=ts1 - ts0,
            test_bars=te1 - te0,
            test_result={
                "per_symbol": results,
                "total_pnl": sum(r["total_pnl"] for r in results.values()),
                "total_trades": sum(r["trades"] for r in results.values()),
                "total_wins": sum(r["wins"] for r in results.values()),
            },
        )
        report.windows.append(w)

        window_pnl = w.test_result["total_pnl"]
        window_trades = w.test_result["total_trades"]
        window_wins = w.test_result["total_wins"]
        test_pnls.append(window_pnl)
        win_rates.append(window_wins / window_trades if window_trades else 0.0)
        final_equities.extend(r["final_equity"] for r in results.values())

    report.combined_test_pnl = sum(test_pnls)
    report.combined_final_equity = sum(final_equities)
    report.avg_win_rate = sum(win_rates) / len(win_rates) if win_rates else 0.0
    profitable = sum(1 for p in test_pnls if p > 0)
    report.consistency = profitable / len(test_pnls) if test_pnls else 0.0
    return report
