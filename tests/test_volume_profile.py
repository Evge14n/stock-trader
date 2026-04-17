from agents.python.volume_profile import analyze_symbol, calculate_profile, interpret_profile


def _make_candles(n: int = 50, start: float = 100) -> list[dict]:
    import math

    candles = []
    for i in range(n):
        mid = start + math.sin(i / 5) * 3 + i * 0.1
        candles.append(
            {
                "timestamp": 1700000000 + i * 86400,
                "open": mid - 0.5,
                "high": mid + 1.5,
                "low": mid - 1.5,
                "close": mid,
                "volume": 1_000_000 + i * 5_000,
            }
        )
    return candles


def test_calculate_profile_short_data():
    profile = calculate_profile([])
    assert profile.point_of_control == 0.0


def test_calculate_profile_basic():
    candles = _make_candles(50)
    profile = calculate_profile(candles)
    assert profile.point_of_control > 0
    assert profile.value_area_low <= profile.point_of_control <= profile.value_area_high


def test_profile_has_histogram():
    candles = _make_candles(50)
    profile = calculate_profile(candles, bins=30)
    assert len(profile.histogram) == 30


def test_profile_has_support_resistance():
    candles = _make_candles(50)
    profile = calculate_profile(candles)
    assert isinstance(profile.support_levels, list)
    assert isinstance(profile.resistance_levels, list)


def test_profile_position_relative():
    candles = _make_candles(50)
    profile = calculate_profile(candles)
    assert profile.position_relative in ("below_value_area", "above_value_area", "inside_value_area")


def test_interpret_empty():
    from agents.python.volume_profile import VolumeProfile

    result = interpret_profile(VolumeProfile())
    assert result["signal"] == "neutral"


def test_analyze_symbol_structure():
    candles = _make_candles(50)
    result = analyze_symbol("TEST", candles)
    for key in ["symbol", "point_of_control", "value_area_high", "value_area_low", "signal"]:
        assert key in result
