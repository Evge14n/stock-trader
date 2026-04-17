from __future__ import annotations

import numpy as np
import pandas as pd

from agents.python.indicators import (
    calc_adx,
    calc_atr,
    calc_bollinger,
    calc_macd,
    calc_rsi,
    calc_sma,
    calc_stochastic,
)


def _safe_ratio(num: float, den: float, fallback: float = 0.0) -> float:
    if den == 0 or pd.isna(den) or pd.isna(num):
        return fallback
    return float(num) / float(den)


def _return(closes: pd.Series, periods: int) -> float:
    if len(closes) <= periods:
        return 0.0
    prev = closes.iloc[-periods - 1]
    curr = closes.iloc[-1]
    if prev == 0 or pd.isna(prev):
        return 0.0
    return float((curr - prev) / prev)


def observation(
    df: pd.DataFrame,
    idx: int,
    has_position: bool,
    entry_price: float = 0.0,
    holding_bars: int = 0,
    max_holding_bars: int = 60,
) -> np.ndarray:
    if idx < 0 or idx >= len(df):
        return np.zeros(13, dtype=np.float32)

    window = df.iloc[: idx + 1]
    closes = window["close"]
    if len(closes) < 26:
        price = float(closes.iloc[-1]) if len(closes) else 0.0
        held = 1.0 if has_position else 0.0
        pnl_pct = _safe_ratio(price - entry_price, entry_price) if has_position else 0.0
        return np.array(
            [0.5, 0.0, 0.5, 0.0, 0.5, 0.5, 0.0, 0.0, 0.0, 0.0, held, pnl_pct, holding_bars / max_holding_bars],
            dtype=np.float32,
        )

    price = float(closes.iloc[-1])
    rsi = calc_rsi(closes)
    macd = calc_macd(closes)
    bb = calc_bollinger(closes)
    atr = calc_atr(window)
    stoch = calc_stochastic(window)
    adx = calc_adx(window)
    sma50_series = calc_sma(closes, 50)
    sma50 = float(sma50_series.iloc[-1]) if not pd.isna(sma50_series.iloc[-1]) else price

    ret_1 = _return(closes, 1)
    ret_5 = _return(closes, 5)
    ret_20 = _return(closes, 20)

    held = 1.0 if has_position else 0.0
    pnl_pct = _safe_ratio(price - entry_price, entry_price) if has_position else 0.0
    holding_norm = min(holding_bars / max_holding_bars, 1.5)

    features = np.array(
        [
            rsi / 100.0,
            _safe_ratio(macd["histogram"], price),
            bb["bb_position"],
            _safe_ratio(atr, price),
            stoch["k"] / 100.0,
            adx / 100.0,
            _safe_ratio(price - sma50, price),
            ret_1,
            ret_5,
            ret_20,
            held,
            pnl_pct,
            holding_norm,
        ],
        dtype=np.float32,
    )

    features = np.nan_to_num(features, nan=0.0, posinf=1.0, neginf=-1.0)
    features = np.clip(features, -5.0, 5.0)
    return features
