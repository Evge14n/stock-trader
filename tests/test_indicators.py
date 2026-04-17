from agents.python.indicators import (
    _to_df,
    calc_adx,
    calc_atr,
    calc_bollinger,
    calc_macd,
    calc_obv,
    calc_rsi,
    calc_stochastic,
    calc_vwap,
)


def test_to_df_empty():
    df = _to_df([])
    assert df.empty


def test_to_df_sorted(sample_ohlcv):
    df = _to_df(sample_ohlcv[::-1])
    assert df.iloc[0]["timestamp"] < df.iloc[-1]["timestamp"]


def test_rsi_in_range(sample_ohlcv):
    df = _to_df(sample_ohlcv)
    rsi = calc_rsi(df["close"])
    assert 0 <= rsi <= 100


def test_rsi_uptrend_is_high():
    import pandas as pd

    closes = pd.Series(list(range(100, 150)))
    rsi = calc_rsi(closes)
    assert rsi > 70


def test_rsi_downtrend_is_low():
    import pandas as pd

    closes = pd.Series(list(range(150, 100, -1)))
    rsi = calc_rsi(closes)
    assert rsi < 30


def test_macd_structure(sample_ohlcv):
    df = _to_df(sample_ohlcv)
    macd = calc_macd(df["close"])
    assert "macd" in macd
    assert "signal" in macd
    assert "histogram" in macd


def test_bollinger_bands_ordering(sample_ohlcv):
    df = _to_df(sample_ohlcv)
    bb = calc_bollinger(df["close"])
    assert bb["lower"] < bb["middle"] < bb["upper"]


def test_bollinger_position_in_range(sample_ohlcv):
    df = _to_df(sample_ohlcv)
    bb = calc_bollinger(df["close"])
    assert -0.1 <= bb["bb_position"] <= 1.1


def test_atr_positive(sample_ohlcv):
    df = _to_df(sample_ohlcv)
    atr = calc_atr(df)
    assert atr > 0


def test_vwap_within_price_range(sample_ohlcv):
    df = _to_df(sample_ohlcv)
    vwap = calc_vwap(df)
    assert df["low"].min() <= vwap <= df["high"].max()


def test_stochastic_in_range(sample_ohlcv):
    df = _to_df(sample_ohlcv)
    stoch = calc_stochastic(df)
    assert 0 <= stoch["k"] <= 100
    assert 0 <= stoch["d"] <= 100


def test_adx_non_negative(sample_ohlcv):
    df = _to_df(sample_ohlcv)
    adx = calc_adx(df)
    assert adx >= 0


def test_obv_computable(sample_ohlcv):
    df = _to_df(sample_ohlcv)
    obv = calc_obv(df)
    assert isinstance(obv, float)
