from __future__ import annotations

import asyncio

from core import llm_client
from core.parser import parse_response
from core.state import Analysis, PipelineState

BULL_SYSTEM = """You are a BULLISH ADVOCATE. Your job is to argue for BUYING this stock.
Find every positive signal in the data. Build the strongest case for going long.
Output ONLY valid JSON: {"verdict": "buy", "confidence": 0.0-1.0, "argument": "your strongest bull thesis in one sentence"}
Even if data is mixed, find bullish angles. But do not lie about numbers."""

BEAR_SYSTEM = """You are a BEARISH ADVOCATE. Your job is to argue against BUYING this stock.
Find every red flag, every risk, every reason to avoid or short. Build the strongest case.
Output ONLY valid JSON: {"verdict": "sell", "confidence": 0.0-1.0, "argument": "your strongest bear thesis in one sentence"}
Even if data is mixed, find bearish angles. But do not lie about numbers."""

JUDGE_SYSTEM = """You are an INVESTMENT COMMITTEE JUDGE. Two analysts presented opposing views.
Evaluate who built the stronger case based on the actual data.
Output ONLY valid JSON: {"signal": "bullish|bearish|neutral", "confidence": 0.0-1.0, "reasoning": "which side won and why"}
If both arguments are weak, return neutral. Strong conviction requires one side significantly outweighing the other."""


def _build_data_prompt(symbol: str, state: PipelineState) -> str:
    md = state.market_data.get(symbol)
    indicators = state.indicators.get(symbol, [])

    lines = [f"Symbol: {symbol}"]
    if md:
        lines.append(f"Price: ${md.price}")

    lines.append("\nIndicators:")
    for ind in indicators[:10]:
        lines.append(f"  {ind.name}: {ind.value} ({ind.signal})")

    analyses = state.analyses.get(symbol, [])
    if analyses:
        lines.append("\nPrior agent analyses:")
        for a in analyses[:8]:
            lines.append(f"  {a.agent}: {a.signal} ({a.confidence:.0%})")

    news = state.news.get(symbol, [])
    if news:
        lines.append(f"\nRecent news ({len(news)} headlines):")
        for n in news[:3]:
            lines.append(f"  - {n.headline[:100]}")

    return "\n".join(lines)


async def _bull_argument(symbol: str, state: PipelineState) -> str:
    data = _build_data_prompt(symbol, state)
    return await llm_client.query(data, system=BULL_SYSTEM, temperature=0.3)


async def _bear_argument(symbol: str, state: PipelineState) -> str:
    data = _build_data_prompt(symbol, state)
    return await llm_client.query(data, system=BEAR_SYSTEM, temperature=0.3)


async def _judge_debate(symbol: str, bull: str, bear: str, state: PipelineState) -> str:
    data = _build_data_prompt(symbol, state)
    prompt = f"{data}\n\n[BULL ARGUMENT]\n{bull[:400]}\n\n[BEAR ARGUMENT]\n{bear[:400]}\n\nVerdict:"
    return await llm_client.query(prompt, system=JUDGE_SYSTEM, temperature=0.2)


async def _debate_one(symbol: str, state: PipelineState) -> Analysis | None:
    if symbol not in state.market_data:
        return None

    bull_response, bear_response = await asyncio.gather(
        _bull_argument(symbol, state),
        _bear_argument(symbol, state),
    )

    judgment = await _judge_debate(symbol, bull_response, bear_response, state)
    signal, confidence = parse_response(judgment, default_signal="neutral")

    reasoning = f"Debate: [BULL] {bull_response[:150]} [BEAR] {bear_response[:150]} [JUDGE] {judgment[:200]}"

    return Analysis(
        agent="debate_judge",
        symbol=symbol,
        signal=signal,
        confidence=confidence,
        reasoning=reasoning[:500],
    )


async def analyze(state: PipelineState) -> PipelineState:
    results = await asyncio.gather(*[_debate_one(s, state) for s in state.symbols])
    for symbol, analysis in zip(state.symbols, results, strict=False):
        if analysis:
            state.analyses.setdefault(symbol, []).append(analysis)
    return state
