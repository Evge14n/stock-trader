from __future__ import annotations

import numpy as np
import pandas as pd

from core.state import Indicator, PipelineState


def _to_df(ohlcv: list[dict]) -> pd.DataFrame:
    if not ohlcv:
        return pd.DataFrame()
    df = pd.DataFrame(ohlcv)
    df = df.sort_values("timestamp").reset_index(drop=True)
    return df


def calc_sma(closes: pd.Series, period: int) -> pd.Series:
    return closes.rolling(window=period).mean()


def calc_ema(closes: pd.Series, period: int) -> pd.Series:
    return closes.ewm(span=period, adjust=False).mean()


def calc_rsi(closes: pd.Series, period: int = 14) -> float:
    delta = closes.diff()
    gain = delta.where(delta > 0, 0.0).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0.0)).rolling(window=period).mean()

    last_gain = gain.iloc[-1] if not gain.empty else 0.0
    last_loss = loss.iloc[-1] if not loss.empty else 0.0

    if pd.isna(last_gain) or pd.isna(last_loss):
        return 50.0
    if last_loss == 0 and last_gain == 0:
        return 50.0
    if last_loss == 0:
        return 100.0
    if last_gain == 0:
        return 0.0

    rs = last_gain / last_loss
    return round(100 - (100 / (1 + rs)), 2)


def calc_macd(closes: pd.Series) -> dict:
    ema12 = calc_ema(closes, 12)
    ema26 = calc_ema(closes, 26)
    macd_line = ema12 - ema26
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    histogram = macd_line - signal_line
    return {
        "macd": round(float(macd_line.iloc[-1]), 4) if not macd_line.empty else 0.0,
        "signal": round(float(signal_line.iloc[-1]), 4) if not signal_line.empty else 0.0,
        "histogram": round(float(histogram.iloc[-1]), 4) if not histogram.empty else 0.0,
    }


def calc_bollinger(closes: pd.Series, period: int = 20, std_dev: float = 2.0) -> dict:
    sma = calc_sma(closes, period)
    std = closes.rolling(window=period).std()
    upper = sma + std_dev * std
    lower = sma - std_dev * std
    price = closes.iloc[-1]
    bb_position = (price - lower.iloc[-1]) / (upper.iloc[-1] - lower.iloc[-1]) if upper.iloc[-1] != lower.iloc[-1] else 0.5
    return {
        "upper": round(float(upper.iloc[-1]), 2),
        "middle": round(float(sma.iloc[-1]), 2),
        "lower": round(float(lower.iloc[-1]), 2),
        "bb_position": round(float(bb_position), 4),
        "bandwidth": round(float((upper.iloc[-1] - lower.iloc[-1]) / sma.iloc[-1]), 4),
    }


def calc_atr(df: pd.DataFrame, period: int = 14) -> float:
    high = df["high"]
    low = df["low"]
    close = df["close"].shift(1)
    tr = pd.concat([high - low, (high - close).abs(), (low - close).abs()], axis=1).max(axis=1)
    atr = tr.rolling(window=period).mean()
    return round(float(atr.iloc[-1]), 4) if not atr.empty and not pd.isna(atr.iloc[-1]) else 0.0


def calc_vwap(df: pd.DataFrame) -> float:
    typical = (df["high"] + df["low"] + df["close"]) / 3
    vwap = (typical * df["volume"]).cumsum() / df["volume"].cumsum()
    return round(float(vwap.iloc[-1]), 2) if not vwap.empty else 0.0


def calc_obv(df: pd.DataFrame) -> float:
    obv = (np.sign(df["close"].diff()) * df["volume"]).fillna(0).cumsum()
    return float(obv.iloc[-1]) if not obv.empty else 0.0


def calc_stochastic(df: pd.DataFrame, period: int = 14) -> dict:
    low_min = df["low"].rolling(window=period).min()
    high_max = df["high"].rolling(window=period).max()
    k = 100 * (df["close"] - low_min) / (high_max - low_min)
    d = k.rolling(window=3).mean()
    return {
        "k": round(float(k.iloc[-1]), 2) if not k.empty and not pd.isna(k.iloc[-1]) else 50.0,
        "d": round(float(d.iloc[-1]), 2) if not d.empty and not pd.isna(d.iloc[-1]) else 50.0,
    }


def calc_adx(df: pd.DataFrame, period: int = 14) -> float:
    high = df["high"]
    low = df["low"]
    close = df["close"]

    plus_dm = high.diff()
    minus_dm = -low.diff()
    plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0.0)
    minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0.0)

    tr = pd.concat([high - low, (high - close.shift(1)).abs(), (low - close.shift(1)).abs()], axis=1).max(axis=1)
    atr = tr.rolling(window=period).mean()

    plus_di = 100 * (plus_dm.rolling(window=period).mean() / atr)
    minus_di = 100 * (minus_dm.rolling(window=period).mean() / atr)
    dx = 100 * ((plus_di - minus_di).abs() / (plus_di + minus_di))
    adx = dx.rolling(window=period).mean()
    return round(float(adx.iloc[-1]), 2) if not adx.empty and not pd.isna(adx.iloc[-1]) else 0.0


def _signal_from_rsi(val: float) -> str:
    if val < 30:
        return "oversold"
    if val > 70:
        return "overbought"
    return "neutral"


def _signal_from_macd(macd: dict) -> str:
    if macd["histogram"] > 0 and macd["macd"] > macd["signal"]:
        return "bullish"
    if macd["histogram"] < 0 and macd["macd"] < macd["signal"]:
        return "bearish"
    return "neutral"


def _signal_from_bb(bb: dict) -> str:
    if bb["bb_position"] < 0.1:
        return "oversold"
    if bb["bb_position"] > 0.9:
        return "overbought"
    return "neutral"


def _signal_from_stoch(stoch: dict) -> str:
    if stoch["k"] < 20:
        return "oversold"
    if stoch["k"] > 80:
        return "overbought"
    return "neutral"


async def compute_all(state: PipelineState) -> PipelineState:
    for symbol, md in state.market_data.items():
        df = _to_df(md.ohlcv)
        if df.empty or len(df) < 26:
            state.add_error(f"indicators [{symbol}]: insufficient data ({len(df)} bars)")
            continue

        closes = df["close"]
        results = []

        rsi = calc_rsi(closes)
        results.append(Indicator(name="RSI", value=rsi, signal=_signal_from_rsi(rsi), details={"period": 14}))

        macd = calc_macd(closes)
        results.append(Indicator(name="MACD", value=macd["histogram"], signal=_signal_from_macd(macd), details=macd))

        bb = calc_bollinger(closes)
        results.append(Indicator(name="BB", value=bb["bb_position"], signal=_signal_from_bb(bb), details=bb))

        atr = calc_atr(df)
        results.append(Indicator(name="ATR", value=atr, signal="high_vol" if atr > closes.iloc[-1] * 0.03 else "normal", details={"period": 14}))

        vwap = calc_vwap(df)
        price = closes.iloc[-1]
        results.append(Indicator(name="VWAP", value=vwap, signal="above" if price > vwap else "below", details={"price": price}))

        obv = calc_obv(df)
        obv_trend = "rising" if obv > 0 else "falling"
        results.append(Indicator(name="OBV", value=obv, signal=obv_trend))

        stoch = calc_stochastic(df)
        results.append(Indicator(name="Stochastic", value=stoch["k"], signal=_signal_from_stoch(stoch), details=stoch))

        adx = calc_adx(df)
        results.append(Indicator(name="ADX", value=adx, signal="trending" if adx > 25 else "ranging", details={"period": 14}))

        sma50 = calc_sma(closes, 50)
        sma200 = calc_sma(closes, 200) if len(closes) >= 200 else pd.Series([np.nan])
        if not pd.isna(sma50.iloc[-1]):
            results.append(Indicator(
                name="SMA50",
                value=round(float(sma50.iloc[-1]), 2),
                signal="above" if price > sma50.iloc[-1] else "below",
            ))
        if len(closes) >= 200 and not pd.isna(sma200.iloc[-1]):
            cross = "golden" if sma50.iloc[-1] > sma200.iloc[-1] else "death"
            results.append(Indicator(
                name="SMA200",
                value=round(float(sma200.iloc[-1]), 2),
                signal=cross,
            ))

        state.indicators[symbol] = results

    return state
