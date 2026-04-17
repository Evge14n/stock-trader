from __future__ import annotations

import asyncio

from core import llm_client
from core.state import Analysis, PipelineState

SYSTEM = """You are a senior equity researcher. Synthesize all analyses into a final recommendation.
Output:
- signal: "strong_buy", "buy", "hold", "sell", or "strong_sell"
- confidence: float 0.0-1.0
- reasoning: one paragraph with your synthesis
Weight: technical 30%, fundamental 25%, momentum 20%, sentiment 15%, volatility 10%.
Only recommend buy/sell when multiple signals align."""


def _build_prompt(symbol: str, state: PipelineState) -> str:
    analyses = state.analyses.get(symbol, [])
    md = state.market_data.get(symbol)

    lines = [f"Symbol: {symbol}"]
    if md:
        lines.append(f"Current price: ${md.price}")

    lines.append("\nAnalyses to synthesize:")
    for a in analyses:
        lines.append(f"\n[{a.agent}] Signal: {a.signal} | Confidence: {a.confidence}")
        lines.append(f"  Reasoning: {a.reasoning[:200]}")

    indicators = state.indicators.get(symbol, [])
    if indicators:
        lines.append("\nKey indicators:")
        for ind in indicators:
            lines.append(f"  {ind.name}: {ind.value} ({ind.signal})")

    return "\n".join(lines)


def _compute_confidence(signals: list[str], base_conf: float) -> float:
    bullish = sum(1 for s in signals if s == "bullish")
    bearish = sum(1 for s in signals if s == "bearish")

    if not signals:
        return base_conf * 0.5

    total = len(signals)
    alignment = max(bullish, bearish) / total

    if alignment >= 0.8:
        return min(base_conf + 0.2, 0.95)
    if alignment >= 0.6:
        return min(base_conf + 0.1, 0.85)
    return base_conf * 0.75


async def _synthesize_one(symbol: str, state: PipelineState) -> Analysis | None:
    if symbol not in state.analyses:
        return None

    prompt = _build_prompt(symbol, state)
    response = await llm_client.query(prompt, system=SYSTEM, temperature=0.2)

    signal = "hold"
    signal_map = {
        "strong_buy": "strong_buy",
        "strong buy": "strong_buy",
        "buy": "buy",
        "strong_sell": "strong_sell",
        "strong sell": "strong_sell",
        "sell": "sell",
        "hold": "hold",
    }
    resp_lower = response.lower()
    for key, val in signal_map.items():
        if key in resp_lower:
            signal = val
            break

    analyses = state.analyses.get(symbol, [])
    avg_conf = sum(a.confidence for a in analyses) / len(analyses) if analyses else 0.5
    signals = [a.signal for a in analyses]
    confidence = _compute_confidence(signals, avg_conf)

    return Analysis(
        agent="researcher",
        symbol=symbol,
        signal=signal,
        confidence=round(confidence, 3),
        reasoning=response[:500],
    )


async def synthesize(state: PipelineState) -> PipelineState:
    results = await asyncio.gather(*[_synthesize_one(s, state) for s in state.symbols])
    for symbol, analysis in zip(state.symbols, results, strict=False):
        if analysis:
            state.analyses.setdefault(symbol, []).append(analysis)
    return state
