from __future__ import annotations

import numpy as np
import pandas as pd

from agents.python.data_collector import fetch_candles


def compute_correlation_matrix(symbols: list[str], period: str = "3mo") -> dict:
    data = {}
    for sym in symbols:
        candles = fetch_candles(sym, period=period)
        if candles:
            closes = [c["close"] for c in candles]
            data[sym] = closes

    if len(data) < 2:
        return {"symbols": list(data.keys()), "matrix": {}, "highly_correlated": []}

    min_len = min(len(v) for v in data.values())
    aligned = {sym: v[-min_len:] for sym, v in data.items()}

    df = pd.DataFrame(aligned)
    returns = df.pct_change().dropna()
    corr = returns.corr()

    matrix = {}
    highly_correlated: list[tuple[str, str, float]] = []

    for sym1 in corr.index:
        matrix[sym1] = {}
        for sym2 in corr.columns:
            val = float(corr.loc[sym1, sym2])
            matrix[sym1][sym2] = round(val, 3)
            if sym1 < sym2 and not np.isnan(val) and val > 0.8:
                highly_correlated.append((sym1, sym2, round(val, 3)))

    return {
        "symbols": list(data.keys()),
        "matrix": matrix,
        "highly_correlated": sorted(highly_correlated, key=lambda x: -x[2]),
    }


def filter_by_correlation(
    symbols: list[str],
    existing_positions: list[str],
    threshold: float = 0.8,
    period: str = "3mo",
) -> list[str]:
    if not existing_positions:
        return symbols

    all_syms = list(set(symbols + existing_positions))
    corr_data = compute_correlation_matrix(all_syms, period=period)
    matrix = corr_data.get("matrix", {})

    filtered = []
    for sym in symbols:
        too_correlated = False
        for held in existing_positions:
            if sym == held:
                too_correlated = True
                break
            corr = matrix.get(sym, {}).get(held)
            if corr is not None and abs(corr) >= threshold:
                too_correlated = True
                break
        if not too_correlated:
            filtered.append(sym)

    return filtered
