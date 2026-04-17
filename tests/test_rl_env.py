from __future__ import annotations

import math

import pandas as pd
import pytest

gym = pytest.importorskip("gymnasium")

from agents.python.rl import ACTION_BUY, ACTION_HOLD, ACTION_SELL, OBS_DIM
from agents.python.rl.env import EnvConfig, TradingEnv


def _trending_df(n: int = 120, slope: float = 0.5) -> pd.DataFrame:
    rows = []
    base = 100.0
    for i in range(n):
        price = base + i * slope + math.sin(i / 7) * 2
        rows.append(
            {
                "timestamp": 1700000000 + i * 86400,
                "open": price - 0.5,
                "high": price + 1.2,
                "low": price - 1.2,
                "close": price,
                "volume": 1_000_000,
            }
        )
    return pd.DataFrame(rows)


def test_reset_returns_valid_observation():
    env = TradingEnv(_trending_df(), EnvConfig())
    obs, _info = env.reset(seed=0)
    assert obs.shape == (OBS_DIM,)
    assert obs[10] == 0.0


def test_buy_sell_cycle_generates_trade():
    env = TradingEnv(_trending_df(), EnvConfig())
    env.reset(seed=0)
    env.step(ACTION_BUY)
    for _ in range(10):
        env.step(ACTION_HOLD)
    _, _, _, _, info = env.step(ACTION_SELL)
    assert info["trade_count"] == 1
    assert info["shares"] == 0


def test_illegal_buy_when_already_long_is_penalised():
    env = TradingEnv(_trending_df(), EnvConfig())
    env.reset(seed=0)
    env.step(ACTION_BUY)
    _, reward, _, _, _ = env.step(ACTION_BUY)
    assert reward < 0


def test_illegal_sell_when_flat_is_penalised():
    env = TradingEnv(_trending_df(), EnvConfig())
    env.reset(seed=0)
    _, reward, _, _, _ = env.step(ACTION_SELL)
    assert reward < 0


def test_full_episode_terminates():
    df = _trending_df(60)
    env = TradingEnv(df, EnvConfig(start_idx=30))
    env.reset(seed=0)
    steps = 0
    done = False
    while not done and steps < 100:
        _, _, done, _, _ = env.step(ACTION_HOLD)
        steps += 1
    assert done
    assert steps < 100


def test_long_only_uptrend_profits_from_buy_hold():
    df = _trending_df(n=200, slope=0.8)
    env = TradingEnv(df, EnvConfig(start_idx=30))
    env.reset(seed=0)
    env.step(ACTION_BUY)
    done = False
    while not done:
        _, _, done, _, _ = env.step(ACTION_HOLD)
    s = env.summary()
    assert s["trades"] >= 1
    assert s["total_pnl"] > 0


def test_summary_handles_empty_trades():
    env = TradingEnv(_trending_df(), EnvConfig())
    env.reset(seed=0)
    s = env.summary()
    assert s["trades"] == 0
    assert s["win_rate"] == 0.0
