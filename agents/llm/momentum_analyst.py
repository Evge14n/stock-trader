from __future__ import annotations
from core import llm_client
from core.state import Analysis, PipelineState

SYSTEM = """You are a momentum analyst. Assess price momentum and trend strength.
Output:
- signal: bullish, bearish, or neutral
- confidence: 0.0-1.0
- reasoning: focus on rate of change, trend continuation probability"""


def _momentum_metrics(md) -> dict:
    if not md or not md.ohlcv or len(md.ohlcv) < 20:
        return {}

    closes = [c["close"] for c in md.ohlcv]
    current = closes[-1]

    change_5d = (current - closes[-5]) / closes[-5] * 100 if len(closes) >= 5 else 0.0
    change_10d = (current - closes[-10]) / closes[-10] * 100 if len(closes) >= 10 else 0.0
    change_20d = (current - closes[-20]) / closes[-20] * 100 if len(closes) >= 20 else 0.0

    gains = sum(1 for i in range(-10, 0) if closes[i] > closes[i - 1])
    losses = 10 - gains

    high_20d = max(c["high"] for c in md.ohlcv[-20:])
    low_20d = min(c["low"] for c in md.ohlcv[-20:])
    dist_from_high = (current - high_20d) / high_20d * 100
    dist_from_low = (current - low_20d) / low_20d * 100

    return {
        "change_5d": round(change_5d, 2),
        "change_10d": round(change_10d, 2),
        "change_20d": round(change_20d, 2),
        "up_days_10d": gains,
        "down_days_10d": losses,
        "dist_from_high_20d": round(dist_from_high, 2),
        "dist_from_low_20d": round(dist_from_low, 2),
    }


def _build_prompt(symbol: str, metrics: dict, price: float) -> str:
    if not metrics:
        return f"Insufficient data for {symbol}. Return neutral."
    return (
        f"Symbol: {symbol}\n"
        f"Current price: ${price:.2f}\n"
        f"5-day change: {metrics['change_5d']:+.2f}%\n"
        f"10-day change: {metrics['change_10d']:+.2f}%\n"
        f"20-day change: {metrics['change_20d']:+.2f}%\n"
        f"Up days (last 10): {metrics['up_days_10d']}\n"
        f"Down days (last 10): {metrics['down_days_10d']}\n"
        f"Distance from 20d high: {metrics['dist_from_high_20d']:.2f}%\n"
        f"Distance from 20d low: {metrics['dist_from_low_20d']:+.2f}%"
    )


async def analyze(state: PipelineState) -> PipelineState:
    for symbol in state.symbols:
        md = state.market_data.get(symbol)
        if not md:
            continue

        metrics = _momentum_metrics(md)
        prompt = _build_prompt(symbol, metrics, md.price)
        response = await llm_client.query(prompt, system=SYSTEM)

        signal = "neutral"
        for s in ["bullish", "bearish", "neutral"]:
            if s in response.lower():
                signal = s
                break

        confidence = 0.5
        if metrics:
            change_20d = metrics.get("change_20d", 0)
            up_days = metrics.get("up_days_10d", 5)
            if change_20d > 5 and up_days >= 7:
                confidence = 0.8
            elif change_20d < -5 and up_days <= 3:
                confidence = 0.75
            elif abs(change_20d) < 2:
                confidence = 0.4

        state.analyses.setdefault(symbol, []).append(Analysis(
            agent="momentum_analyst",
            symbol=symbol,
            signal=signal,
            confidence=round(confidence, 3),
            reasoning=response[:500],
        ))
    return state
