from __future__ import annotations

import asyncio

import pandas as pd
import yfinance as yf

from agents.python.indicators import calc_bollinger, calc_macd, calc_rsi
from core.state import Analysis, PipelineState


def _fetch_candles_tf(symbol: str, period: str, interval: str) -> pd.DataFrame:
    try:
        hist = yf.Ticker(symbol).history(period=period, interval=interval)
        if hist.empty:
            return pd.DataFrame()
        df = hist.rename(columns={"Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"})
        df = df.reset_index(drop=True)
        return df
    except Exception:
        return pd.DataFrame()


def _score_timeframe(df: pd.DataFrame) -> tuple[str, float]:
    if df.empty or len(df) < 30:
        return "neutral", 0.0

    closes = df["close"]
    rsi = calc_rsi(closes)
    macd = calc_macd(closes)
    bb = calc_bollinger(closes)

    score = 0.0

    if rsi < 35:
        score += 1
    elif rsi > 70:
        score -= 1

    if macd["histogram"] > 0 and macd["macd"] > macd["signal"]:
        score += 1
    elif macd["histogram"] < 0 and macd["macd"] < macd["signal"]:
        score -= 1

    if bb["bb_position"] < 0.25:
        score += 1
    elif bb["bb_position"] > 0.85:
        score -= 1

    if score >= 2:
        return "bullish", min(0.9, 0.5 + score * 0.15)
    if score <= -2:
        return "bearish", min(0.9, 0.5 + abs(score) * 0.15)
    return "neutral", 0.5


def analyze_symbol_multi_tf(symbol: str) -> dict:
    timeframes = {
        "1h": ("5d", "1h"),
        "1d": ("3mo", "1d"),
        "1wk": ("2y", "1wk"),
    }

    results = {}
    for tf_name, (period, interval) in timeframes.items():
        df = _fetch_candles_tf(symbol, period, interval)
        signal, confidence = _score_timeframe(df)
        results[tf_name] = {"signal": signal, "confidence": confidence}

    signals = [r["signal"] for r in results.values()]
    bullish_count = signals.count("bullish")
    bearish_count = signals.count("bearish")

    if bullish_count >= 2:
        confluence = "bullish"
        confluence_conf = min(0.95, 0.6 + bullish_count * 0.1)
    elif bearish_count >= 2:
        confluence = "bearish"
        confluence_conf = min(0.95, 0.6 + bearish_count * 0.1)
    else:
        confluence = "neutral"
        confluence_conf = 0.4

    return {
        "symbol": symbol,
        "timeframes": results,
        "confluence_signal": confluence,
        "confluence_confidence": round(confluence_conf, 3),
    }


async def analyze(state: PipelineState) -> PipelineState:
    async def _process(symbol: str):
        if symbol not in state.market_data:
            return None
        return await asyncio.to_thread(analyze_symbol_multi_tf, symbol)

    results = await asyncio.gather(*[_process(s) for s in state.symbols])

    for result in results:
        if not result:
            continue

        tfs = result["timeframes"]
        reasoning = f"1h: {tfs['1h']['signal']}, 1d: {tfs['1d']['signal']}, 1w: {tfs['1wk']['signal']}. Confluence: {result['confluence_signal']}"

        state.analyses.setdefault(result["symbol"], []).append(
            Analysis(
                agent="multi_timeframe",
                symbol=result["symbol"],
                signal=result["confluence_signal"],
                confidence=result["confluence_confidence"],
                reasoning=reasoning,
            )
        )

    return state
