from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar

import numpy as np
import pandas as pd

try:
    import gymnasium as gym
    from gymnasium import spaces

    _GYM_AVAILABLE = True
except ImportError:
    gym = None
    spaces = None
    _GYM_AVAILABLE = False

from agents.python.rl import ACTION_BUY, ACTION_SELL, OBS_DIM
from agents.python.rl.features import observation


@dataclass
class EnvConfig:
    initial_cash: float = 10_000.0
    position_pct: float = 0.95
    commission_pct: float = 0.001
    slippage_pct: float = 0.0005
    start_idx: int = 30
    max_holding_bars: int = 60
    illegal_action_penalty: float = 0.01


class TradingEnv(gym.Env if _GYM_AVAILABLE else object):
    metadata: ClassVar[dict] = {"render_modes": []}

    def __init__(self, df: pd.DataFrame, config: EnvConfig | None = None):
        if not _GYM_AVAILABLE:
            raise ImportError("gymnasium not installed; pip install -r requirements-rl.txt")

        super().__init__()
        if df.empty or len(df) <= 30:
            raise ValueError(f"insufficient bars for episode: {len(df)}")

        self.df = df.reset_index(drop=True)
        self.config = config or EnvConfig()
        self.action_space = spaces.Discrete(3)
        self.observation_space = spaces.Box(low=-5.0, high=5.0, shape=(OBS_DIM,), dtype=np.float32)

        self._idx = 0
        self._cash = 0.0
        self._shares = 0
        self._entry_price = 0.0
        self._holding_bars = 0
        self._prev_equity = 0.0
        self._trades: list[dict] = []

    def reset(self, *, seed: int | None = None, options: dict | None = None) -> tuple[np.ndarray, dict]:
        super().reset(seed=seed)
        self._idx = self.config.start_idx
        self._cash = self.config.initial_cash
        self._shares = 0
        self._entry_price = 0.0
        self._holding_bars = 0
        self._prev_equity = self._cash
        self._trades = []
        return self._obs(), {}

    def step(self, action: int) -> tuple[np.ndarray, float, bool, bool, dict]:
        price = self._price()
        illegal = False

        if action == ACTION_BUY:
            if self._shares == 0:
                self._open_long(price)
            else:
                illegal = True
        elif action == ACTION_SELL:
            if self._shares > 0:
                self._close_long(price)
            else:
                illegal = True

        if self._shares > 0:
            self._holding_bars += 1

        self._idx += 1
        done = self._idx >= len(self.df) - 1

        if done and self._shares > 0:
            self._close_long(self._price())

        equity = self._equity()
        reward = (equity - self._prev_equity) / self.config.initial_cash
        if illegal:
            reward -= self.config.illegal_action_penalty
        self._prev_equity = equity

        info = {
            "equity": equity,
            "shares": self._shares,
            "cash": self._cash,
            "trade_count": len(self._trades),
        }
        return self._obs(), float(reward), done, False, info

    def _price(self) -> float:
        return float(self.df.iloc[self._idx]["close"])

    def _obs(self) -> np.ndarray:
        return observation(
            self.df,
            idx=self._idx,
            has_position=self._shares > 0,
            entry_price=self._entry_price,
            holding_bars=self._holding_bars,
            max_holding_bars=self.config.max_holding_bars,
        )

    def _equity(self) -> float:
        return self._cash + self._shares * self._price()

    def _open_long(self, price: float) -> None:
        fill_price = price * (1 + self.config.slippage_pct)
        budget = self._cash * self.config.position_pct
        qty = int(budget / fill_price)
        if qty <= 0:
            return
        cost = qty * fill_price
        fee = cost * self.config.commission_pct
        if cost + fee > self._cash:
            return
        self._cash -= cost + fee
        self._shares = qty
        self._entry_price = fill_price
        self._holding_bars = 0

    def _close_long(self, price: float) -> None:
        if self._shares <= 0:
            return
        fill_price = price * (1 - self.config.slippage_pct)
        proceeds = self._shares * fill_price
        fee = proceeds * self.config.commission_pct
        pnl = proceeds - fee - self._shares * self._entry_price
        self._cash += proceeds - fee
        self._trades.append(
            {
                "entry": self._entry_price,
                "exit": fill_price,
                "qty": self._shares,
                "pnl": pnl,
                "holding_bars": self._holding_bars,
            }
        )
        self._shares = 0
        self._entry_price = 0.0
        self._holding_bars = 0

    def summary(self) -> dict[str, Any]:
        wins = [t for t in self._trades if t["pnl"] > 0]
        return {
            "trades": len(self._trades),
            "wins": len(wins),
            "win_rate": len(wins) / len(self._trades) if self._trades else 0.0,
            "total_pnl": sum(t["pnl"] for t in self._trades),
            "final_equity": self._equity(),
        }
