import pandas as pd
import pytest

from agents.strategies.base import STRATEGIES, BBMeanReversion, Momentum, MomentumBreakout, get_strategy


@pytest.fixture
def trending_up_df():
    data = []
    for i in range(60):
        price = 100 + i * 0.5
        data.append(
            {
                "timestamp": 1700000000 + i * 86400,
                "open": price - 0.5,
                "high": price + 1,
                "low": price - 1,
                "close": price,
                "volume": 1_000_000,
            }
        )
    return pd.DataFrame(data)


@pytest.fixture
def trending_down_df():
    data = []
    for i in range(60):
        price = 100 - i * 0.5
        data.append(
            {
                "timestamp": 1700000000 + i * 86400,
                "open": price + 0.5,
                "high": price + 1,
                "low": price - 1,
                "close": price,
                "volume": 1_000_000,
            }
        )
    return pd.DataFrame(data)


def test_strategy_registry():
    assert "bb_mean_reversion" in STRATEGIES
    assert "momentum" in STRATEGIES
    assert "momentum_breakout" in STRATEGIES


def test_get_strategy_default_on_unknown():
    s = get_strategy("nonexistent")
    assert isinstance(s, BBMeanReversion)


def test_get_strategy_known():
    assert isinstance(get_strategy("momentum"), Momentum)
    assert isinstance(get_strategy("momentum_breakout"), MomentumBreakout)


def test_bb_mean_reversion_short_data(trending_up_df):
    s = BBMeanReversion()
    assert s.signal(trending_up_df, 10) == "hold"


def test_bb_mean_reversion_returns_valid_signal(trending_up_df):
    s = BBMeanReversion()
    sig = s.signal(trending_up_df, 50)
    assert sig in ("buy", "sell", "hold")


def test_momentum_breakout_no_volume_spike(trending_up_df):
    s = MomentumBreakout()
    sig = s.signal(trending_up_df, 50)
    assert sig in ("buy", "sell", "hold")


def test_momentum_returns_valid_signal(trending_up_df):
    s = Momentum()
    sig = s.signal(trending_up_df, 50)
    assert sig in ("buy", "sell", "hold")


def test_momentum_short_data(trending_up_df):
    s = Momentum()
    assert s.signal(trending_up_df, 10) == "hold"
