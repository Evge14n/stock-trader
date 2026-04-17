from __future__ import annotations

import asyncio

from core import llm_client
from core.state import Analysis, PipelineState

SYSTEM = """You are a financial news sentiment analyst. Analyze the provided news headlines for a stock.
Output a JSON object with exactly these fields:
- signal: "bullish", "bearish", or "neutral"
- confidence: float 0.0-1.0
- reasoning: one paragraph with key themes from the news
Focus on material news that could move the stock price. Ignore noise."""


def _build_prompt(symbol: str, state: PipelineState) -> str:
    news = state.news.get(symbol, [])
    if not news:
        return f"No recent news found for {symbol}. Return neutral signal."

    lines = [f"Symbol: {symbol}", f"Recent headlines ({len(news)} articles):", ""]
    for item in news:
        sentiment_tag = ""
        if item.sentiment > 0.6:
            sentiment_tag = " [API: positive]"
        elif item.sentiment < 0.4:
            sentiment_tag = " [API: negative]"
        lines.append(f"- {item.headline}{sentiment_tag} ({item.source}, {item.timestamp[:10]})")

    return "\n".join(lines)


def _parse_response(response: str, news_count: int) -> tuple[str, float]:
    signal = "neutral"
    for s in ["bullish", "bearish", "neutral"]:
        if s in response.lower():
            signal = s
            break

    confidence = 0.5
    if news_count >= 5:
        confidence = 0.65
    if any(kw in response.lower() for kw in ["earnings", "acquisition", "fda", "lawsuit", "sec"]):
        confidence = min(confidence + 0.15, 0.95)
    return signal, confidence


async def _analyze_one(symbol: str, state: PipelineState) -> Analysis:
    news = state.news.get(symbol, [])
    if not news:
        return Analysis(
            agent="news_analyst",
            symbol=symbol,
            signal="neutral",
            confidence=0.3,
            reasoning="No recent news available.",
        )

    prompt = _build_prompt(symbol, state)
    response = await llm_client.query(prompt, system=SYSTEM)
    signal, confidence = _parse_response(response, len(news))
    return Analysis(
        agent="news_analyst",
        symbol=symbol,
        signal=signal,
        confidence=confidence,
        reasoning=response[:500],
    )


async def analyze(state: PipelineState) -> PipelineState:
    results = await asyncio.gather(*[_analyze_one(s, state) for s in state.symbols])
    for symbol, analysis in zip(state.symbols, results, strict=False):
        state.analyses.setdefault(symbol, []).append(analysis)
    return state
