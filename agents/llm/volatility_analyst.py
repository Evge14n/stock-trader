from __future__ import annotations

import asyncio
import math

from core import llm_client
from core.state import Analysis, PipelineState

SYSTEM = """You are a volatility analyst. Assess risk profile and position sizing implications.
Output:
- signal: bullish, bearish, or neutral (bullish = low risk entry opportunity, bearish = avoid)
- confidence: 0.0-1.0
- reasoning: comment on realized vol, ATR, and whether risk is priced in"""


def _volatility_metrics(md) -> dict:
    if not md or not md.ohlcv or len(md.ohlcv) < 20:
        return {}

    closes = [c["close"] for c in md.ohlcv]
    returns = [(closes[i] - closes[i - 1]) / closes[i - 1] for i in range(1, len(closes))]

    if not returns:
        return {}

    recent = returns[-20:]
    mean_r = sum(recent) / len(recent)
    var_r = sum((r - mean_r) ** 2 for r in recent) / len(recent)
    daily_vol = math.sqrt(var_r)
    annualized_vol = daily_vol * math.sqrt(252) * 100

    max_up = max(recent) * 100
    max_down = min(recent) * 100

    current = closes[-1]
    high_20d = max(c["high"] for c in md.ohlcv[-20:])
    low_20d = min(c["low"] for c in md.ohlcv[-20:])
    range_pct = (high_20d - low_20d) / low_20d * 100

    return {
        "daily_vol": round(daily_vol * 100, 2),
        "annualized_vol": round(annualized_vol, 2),
        "max_up_day": round(max_up, 2),
        "max_down_day": round(max_down, 2),
        "range_20d_pct": round(range_pct, 2),
        "current_price": current,
    }


def _build_prompt(symbol: str, metrics: dict) -> str:
    if not metrics:
        return f"Insufficient data for {symbol}. Return neutral."
    return (
        f"Symbol: {symbol}\n"
        f"Daily vol (stdev): {metrics['daily_vol']:.2f}%\n"
        f"Annualized vol: {metrics['annualized_vol']:.2f}%\n"
        f"Max up day (20d): {metrics['max_up_day']:+.2f}%\n"
        f"Max down day (20d): {metrics['max_down_day']:+.2f}%\n"
        f"20-day range: {metrics['range_20d_pct']:.2f}%\n\n"
        "Context: annual vol <20% = low risk stock, 20-40% = normal, >40% = high risk.\n"
        "Assess if the current vol regime favors entering a position."
    )


async def _analyze_one(symbol: str, state: PipelineState) -> Analysis | None:
    md = state.market_data.get(symbol)
    if not md:
        return None

    metrics = _volatility_metrics(md)
    prompt = _build_prompt(symbol, metrics)
    response = await llm_client.query(prompt, system=SYSTEM)

    signal = "neutral"
    for s in ["bullish", "bearish", "neutral"]:
        if s in response.lower():
            signal = s
            break

    confidence = 0.5
    if metrics:
        ann = metrics.get("annualized_vol", 30)
        if ann < 25:
            confidence = 0.7
        elif ann > 50:
            confidence = 0.75
        else:
            confidence = 0.55

    return Analysis(
        agent="volatility_analyst",
        symbol=symbol,
        signal=signal,
        confidence=round(confidence, 3),
        reasoning=response[:500],
    )


async def analyze(state: PipelineState) -> PipelineState:
    results = await asyncio.gather(*[_analyze_one(s, state) for s in state.symbols])
    for symbol, analysis in zip(state.symbols, results, strict=False):
        if analysis:
            state.analyses.setdefault(symbol, []).append(analysis)
    return state
