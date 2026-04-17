from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd


class Strategy(ABC):
    name: str = "base"

    @abstractmethod
    def signal(self, df: pd.DataFrame, i: int) -> str: ...


class BBMeanReversion(Strategy):
    name = "bb_mean_reversion"

    def signal(self, df: pd.DataFrame, i: int) -> str:
        from agents.python.indicators import calc_bollinger, calc_macd, calc_rsi

        if i < 30:
            return "hold"

        closes = df.iloc[: i + 1]["close"]
        rsi = calc_rsi(closes)
        bb = calc_bollinger(closes)
        macd = calc_macd(closes)

        score = 0
        if rsi < 35:
            score += 2
        elif rsi < 45:
            score += 1
        if bb["bb_position"] < 0.25:
            score += 2
        elif bb["bb_position"] < 0.4:
            score += 1
        if macd["histogram"] > 0:
            score += 1

        if score >= 3:
            return "buy"
        if rsi > 70 and bb["bb_position"] > 0.85:
            return "sell"
        return "hold"


class MomentumBreakout(Strategy):
    name = "momentum_breakout"

    def signal(self, df: pd.DataFrame, i: int) -> str:
        if i < 30:
            return "hold"

        window = df.iloc[max(0, i - 19) : i + 1]
        recent_close = df.iloc[i]["close"]
        prev_close = df.iloc[i - 1]["close"]

        high_20 = window["high"].iloc[:-1].max()
        low_20 = window["low"].iloc[:-1].min()

        vol_avg = window["volume"].iloc[:-1].mean()
        vol_today = df.iloc[i]["volume"]

        if recent_close > high_20 and vol_today > vol_avg * 1.3 and recent_close > prev_close:
            return "buy"
        if recent_close < low_20 and vol_today > vol_avg * 1.3:
            return "sell"
        return "hold"


class Momentum(Strategy):
    name = "momentum"

    def signal(self, df: pd.DataFrame, i: int) -> str:
        from agents.python.indicators import calc_adx, calc_macd, calc_rsi

        if i < 30:
            return "hold"

        window = df.iloc[: i + 1]
        closes = window["close"]

        rsi = calc_rsi(closes)
        macd = calc_macd(closes)
        adx = calc_adx(window)

        score = 0
        if adx > 25:
            score += 2
        if macd["histogram"] > 0 and macd["macd"] > macd["signal"]:
            score += 2
        if 50 < rsi < 70:
            score += 1

        change_5d = (closes.iloc[-1] - closes.iloc[-6]) / closes.iloc[-6] if len(closes) >= 6 else 0
        if change_5d > 0.02:
            score += 1

        if score >= 4:
            return "buy"
        if adx > 25 and macd["histogram"] < 0 and rsi < 40:
            return "sell"
        return "hold"


STRATEGIES: dict[str, type[Strategy]] = {
    BBMeanReversion.name: BBMeanReversion,
    MomentumBreakout.name: MomentumBreakout,
    Momentum.name: Momentum,
}


def get_strategy(name: str) -> Strategy:
    cls = STRATEGIES.get(name, BBMeanReversion)
    return cls()
