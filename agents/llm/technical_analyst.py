from __future__ import annotations

import asyncio

from core import llm_client
from core.state import Analysis, PipelineState

SYSTEM = """You are a senior technical analyst. Analyze the provided indicators and price data.
Output a JSON object with exactly these fields:
- signal: "bullish", "bearish", or "neutral"
- confidence: float 0.0-1.0
- reasoning: one paragraph explaining your analysis
Be concise. Focus on confluence of signals."""


def _build_prompt(symbol: str, state: PipelineState) -> str:
    md = state.market_data.get(symbol)
    indicators = state.indicators.get(symbol, [])

    lines = [f"Symbol: {symbol}", f"Price: ${md.price}" if md else ""]
    for ind in indicators:
        lines.append(f"{ind.name}: {ind.value} ({ind.signal})")
        if ind.details:
            for k, v in ind.details.items():
                lines.append(f"  {k}: {v}")

    if md and md.ohlcv:
        recent = md.ohlcv[-5:]
        lines.append("\nLast 5 daily candles:")
        for c in recent:
            lines.append(f"  O:{c['open']} H:{c['high']} L:{c['low']} C:{c['close']} V:{c['volume']}")

    return "\n".join(lines)


def _parse_response(response: str) -> tuple[str, float]:
    signal = "neutral"
    for s in ["bullish", "bearish", "neutral"]:
        if s in response.lower():
            signal = s
            break

    confidence = 0.5
    markers = {"high confidence": 0.85, "strong": 0.8, "moderate": 0.6, "weak": 0.4, "low confidence": 0.3}
    for marker, val in markers.items():
        if marker in response.lower():
            confidence = val
            break
    return signal, confidence


async def _analyze_one(symbol: str, state: PipelineState) -> Analysis | None:
    if symbol not in state.market_data:
        return None
    prompt = _build_prompt(symbol, state)
    response = await llm_client.query(prompt, system=SYSTEM)
    signal, confidence = _parse_response(response)
    return Analysis(
        agent="technical_analyst",
        symbol=symbol,
        signal=signal,
        confidence=confidence,
        reasoning=response[:500],
    )


async def analyze(state: PipelineState) -> PipelineState:
    results = await asyncio.gather(*[_analyze_one(s, state) for s in state.symbols])
    for symbol, analysis in zip(state.symbols, results, strict=False):
        if analysis:
            state.analyses.setdefault(symbol, []).append(analysis)
    return state
