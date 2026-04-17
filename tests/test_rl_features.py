from __future__ import annotations

import math

import numpy as np
import pandas as pd

from agents.python.rl.features import observation


def _make_df(n: int = 60) -> pd.DataFrame:
    rows = []
    base = 100.0
    for i in range(n):
        drift = math.sin(i / 8) * 3 + i * 0.2
        price = base + drift
        rows.append(
            {
                "timestamp": 1700000000 + i * 86400,
                "open": price - 0.5,
                "high": price + 1.5,
                "low": price - 1.5,
                "close": price,
                "volume": 1_000_000 + i * 5_000,
            }
        )
    return pd.DataFrame(rows)


def test_observation_shape_flat_no_position():
    df = _make_df()
    obs = observation(df, idx=50, has_position=False)
    assert obs.shape == (13,)
    assert obs.dtype == np.float32
    assert not np.isnan(obs).any()
    assert obs[10] == 0.0
    assert obs[11] == 0.0
    assert obs[12] == 0.0


def test_observation_with_position_has_pnl():
    df = _make_df()
    entry = float(df.iloc[40]["close"])
    obs = observation(df, idx=50, has_position=True, entry_price=entry, holding_bars=10)
    assert obs[10] == 1.0
    assert obs[12] > 0
    current = float(df.iloc[50]["close"])
    expected_pnl = (current - entry) / entry
    assert math.isclose(obs[11], expected_pnl, rel_tol=1e-4)


def test_observation_clipped_range():
    df = _make_df()
    obs = observation(df, idx=50, has_position=False)
    assert obs.min() >= -5.0
    assert obs.max() <= 5.0


def test_observation_short_window_returns_fallback():
    df = _make_df(10)
    obs = observation(df, idx=5, has_position=False)
    assert obs.shape == (13,)
    assert not np.isnan(obs).any()
