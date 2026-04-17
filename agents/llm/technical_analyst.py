from __future__ import annotations

import asyncio

from core import llm_client
from core.parser import parse_response
from core.state import Analysis, PipelineState

SYSTEM = """You are a senior technical analyst. Output ONLY valid JSON:
{"signal": "bullish|bearish|neutral", "confidence": 0.0-1.0, "reasoning": "one sentence"}

Example:
Input: RSI=28, BB=0.1, MACD positive
Output: {"signal": "bullish", "confidence": 0.8, "reasoning": "Oversold RSI with positive MACD suggests mean reversion bounce"}

Rules: confluence of 2+ indicators needed for strong signal. Strict JSON only."""


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


async def _analyze_one(symbol: str, state: PipelineState) -> Analysis | None:
    if symbol not in state.market_data:
        return None
    prompt = _build_prompt(symbol, state)
    response = await llm_client.query(prompt, system=SYSTEM)
    signal, confidence = parse_response(response)
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
