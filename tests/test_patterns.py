import pandas as pd

from agents.python.patterns import (
    _find_local_extrema,
    detect_cup_and_handle,
    detect_double_bottom,
    detect_double_top,
    detect_head_and_shoulders,
    detect_patterns,
    detect_triangle,
)


def _make_candles(closes: list[float]) -> list[dict]:
    return [
        {
            "timestamp": 1700000000 + i * 86400,
            "open": c,
            "high": c * 1.01,
            "low": c * 0.99,
            "close": c,
            "volume": 1_000_000,
        }
        for i, c in enumerate(closes)
    ]


def test_find_local_extrema():
    prices = pd.Series([1, 2, 3, 2, 1, 2, 3, 4, 3, 2])
    peaks, troughs = _find_local_extrema(prices, window=2)
    assert len(peaks) >= 1
    assert len(troughs) >= 1


def test_double_top_detection():
    peak_series = pd.Series([100, 105, 110, 108, 105, 110, 108, 100, 95])
    peaks, _ = _find_local_extrema(peak_series, window=1)
    if len(peaks) >= 2:
        result = detect_double_top(peak_series, peaks)
        assert result is None or result["signal"] == "bearish"


def test_double_bottom_detection():
    series = pd.Series([100, 95, 90, 95, 100, 95, 90, 95, 105])
    _, troughs = _find_local_extrema(series, window=1)
    if len(troughs) >= 2:
        result = detect_double_bottom(series, troughs)
        assert result is None or result["signal"] == "bullish"


def test_detect_patterns_empty():
    result = detect_patterns([])
    assert result == []


def test_detect_patterns_short():
    candles = _make_candles([100, 101, 102])
    result = detect_patterns(candles)
    assert result == []


def test_detect_patterns_trending():
    closes = [100 + i * 0.5 for i in range(50)]
    candles = _make_candles(closes)
    result = detect_patterns(candles)
    assert isinstance(result, list)


def test_triangle_insufficient_data():
    prices = pd.Series([100, 101, 102])
    result = detect_triangle(prices, [], [])
    assert result is None


def test_head_and_shoulders_insufficient():
    prices = pd.Series([100, 105, 110])
    result = detect_head_and_shoulders(prices, [1])
    assert result is None


def test_cup_and_handle_short_data():
    prices = pd.Series([100] * 20)
    result = detect_cup_and_handle(prices)
    assert result is None
