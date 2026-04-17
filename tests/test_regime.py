import math

import pytest

from agents.python.regime_detector import detect_portfolio_regime, detect_regime, pick_strategy


@pytest.fixture
def bull_candles():
    return [
        {
            "timestamp": 1700000000 + i * 86400,
            "open": 100 + i * 0.8,
            "high": 100 + i * 0.8 + 2,
            "low": 100 + i * 0.8 - 1,
            "close": 100 + i * 0.8,
            "volume": 1_000_000,
        }
        for i in range(60)
    ]


@pytest.fixture
def bear_candles():
    return [
        {
            "timestamp": 1700000000 + i * 86400,
            "open": 100 - i * 0.8,
            "high": 100 - i * 0.8 + 1,
            "low": 100 - i * 0.8 - 2,
            "close": 100 - i * 0.8,
            "volume": 1_000_000,
        }
        for i in range(60)
    ]


@pytest.fixture
def choppy_candles():
    return [
        {
            "timestamp": 1700000000 + i * 86400,
            "open": 100 + math.sin(i / 3) * 1,
            "high": 100 + math.sin(i / 3) * 1 + 0.5,
            "low": 100 + math.sin(i / 3) * 1 - 0.5,
            "close": 100 + math.sin(i / 3) * 1,
            "volume": 1_000_000,
        }
        for i in range(60)
    ]


def test_detect_regime_short_data():
    result = detect_regime([{"timestamp": 1, "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1}])
    assert result["regime"] == "unknown"


def test_detect_bull_trend(bull_candles):
    result = detect_regime(bull_candles)
    assert result["regime"] in ("bull_trend", "neutral")
    assert result["metrics"]["change_20d_pct"] > 0


def test_detect_bear_trend(bear_candles):
    result = detect_regime(bear_candles)
    assert result["regime"] in ("bear_trend", "neutral")
    assert result["metrics"]["change_20d_pct"] < 0


def test_pick_strategy_mapping():
    assert pick_strategy("bull_trend") == "momentum"
    assert pick_strategy("low_vol_range") == "bb_mean_reversion"
    assert pick_strategy("high_vol") == "momentum_breakout"
    assert pick_strategy("unknown") == "bb_mean_reversion"


def test_detect_portfolio_empty():
    result = detect_portfolio_regime({})
    assert result["regime"] == "unknown"


def test_detect_portfolio_regime(bull_candles, bear_candles):
    result = detect_portfolio_regime({"A": bull_candles, "B": bull_candles, "C": bear_candles})
    assert "regime" in result
    assert "strategy" in result
    assert result["dominance_pct"] >= 0
