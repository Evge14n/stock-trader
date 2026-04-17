from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations

import numpy as np

from agents.python.data_collector import fetch_candles


@dataclass
class PairSignal:
    symbol_long: str = ""
    symbol_short: str = ""
    spread: float = 0.0
    spread_mean: float = 0.0
    spread_std: float = 0.0
    z_score: float = 0.0
    correlation: float = 0.0
    cointegration_score: float = 0.0
    signal: str = "hold"
    entry_threshold: float = 2.0
    exit_threshold: float = 0.5


def _engle_granger_test(y: np.ndarray, x: np.ndarray) -> tuple[float, np.ndarray]:
    n = len(y)
    if n < 30 or len(x) != n:
        return 1.0, np.array([])

    x_mean = x.mean()
    y_mean = y.mean()
    beta = np.sum((x - x_mean) * (y - y_mean)) / np.sum((x - x_mean) ** 2)
    alpha = y_mean - beta * x_mean
    residuals = y - (alpha + beta * x)

    residual_changes = np.diff(residuals)
    residual_lags = residuals[:-1]

    if np.sum(residual_lags**2) == 0:
        return 1.0, residuals

    coef = np.sum(residual_lags * residual_changes) / np.sum(residual_lags**2)
    se = np.std(residual_changes - coef * residual_lags) / np.sqrt(np.sum(residual_lags**2))

    if se == 0:
        return 1.0, residuals

    t_stat = coef / se
    stationarity_score = max(0, min(1, (-t_stat - 1.5) / 2))

    return stationarity_score, residuals


def find_cointegrated_pairs(symbols: list[str], period: str = "6mo", min_score: float = 0.3) -> list[PairSignal]:
    price_data = {}
    for sym in symbols:
        candles = fetch_candles(sym, period=period)
        if len(candles) >= 30:
            closes = [c["close"] for c in candles]
            price_data[sym] = np.array(closes)

    if len(price_data) < 2:
        return []

    min_len = min(len(v) for v in price_data.values())
    price_data = {k: v[-min_len:] for k, v in price_data.items()}

    pairs = []
    for sym1, sym2 in combinations(price_data.keys(), 2):
        y = price_data[sym1]
        x = price_data[sym2]

        corr = np.corrcoef(y, x)[0, 1]
        if abs(corr) < 0.7:
            continue

        score, residuals = _engle_granger_test(y, x)
        if score < min_score or len(residuals) == 0:
            continue

        spread = residuals[-1]
        spread_mean = residuals.mean()
        spread_std = residuals.std()
        z = (spread - spread_mean) / spread_std if spread_std > 0 else 0

        signal = "hold"
        if z > 2.0:
            signal = "short_y_long_x"
        elif z < -2.0:
            signal = "long_y_short_x"
        elif abs(z) < 0.5:
            signal = "exit"

        pair = PairSignal(
            symbol_long=sym1 if z < 0 else sym2,
            symbol_short=sym2 if z < 0 else sym1,
            spread=round(float(spread), 4),
            spread_mean=round(float(spread_mean), 4),
            spread_std=round(float(spread_std), 4),
            z_score=round(float(z), 3),
            correlation=round(float(corr), 3),
            cointegration_score=round(float(score), 3),
            signal=signal,
        )
        pairs.append(pair)

    pairs.sort(key=lambda p: abs(p.z_score), reverse=True)
    return pairs


def get_best_pair_opportunities(symbols: list[str], period: str = "6mo", top_n: int = 5) -> list[dict]:
    pairs = find_cointegrated_pairs(symbols, period=period)

    opportunities = []
    for p in pairs[:top_n]:
        if p.signal in ("long_y_short_x", "short_y_long_x"):
            opportunities.append(
                {
                    "pair": f"{p.symbol_long}/{p.symbol_short}",
                    "long": p.symbol_long,
                    "short": p.symbol_short,
                    "z_score": p.z_score,
                    "correlation": p.correlation,
                    "cointegration": p.cointegration_score,
                    "signal": p.signal,
                    "action": f"Long {p.symbol_long}, Short {p.symbol_short}",
                    "rationale": f"Spread {p.z_score:+.2f}σ from mean, expect reversion to {p.spread_mean:.2f}",
                }
            )

    return opportunities
