from __future__ import annotations
from core import llm_client
from core.state import Analysis, PipelineState

SYSTEM = """You are a senior equity researcher. Synthesize technical and sentiment analyses into a final recommendation.
Output a JSON object with:
- signal: "strong_buy", "buy", "hold", "sell", or "strong_sell"
- confidence: float 0.0-1.0
- reasoning: one paragraph with your synthesis
Weight technical analysis 60% and sentiment 40%. Only recommend buy/sell when both align."""


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


async def synthesize(state: PipelineState) -> PipelineState:
    for symbol in state.symbols:
        if symbol not in state.analyses:
            continue

        prompt = _build_prompt(symbol, state)
        response = await llm_client.query(prompt, system=SYSTEM, temperature=0.2)

        signal = "hold"
        signal_map = {"strong_buy": "strong_buy", "strong buy": "strong_buy", "buy": "buy",
                      "strong_sell": "strong_sell", "strong sell": "strong_sell", "sell": "sell", "hold": "hold"}
        resp_lower = response.lower()
        for key, val in signal_map.items():
            if key in resp_lower:
                signal = val
                break

        confidence = 0.5
        analyses = state.analyses.get(symbol, [])
        if analyses:
            avg = sum(a.confidence for a in analyses) / len(analyses)
            signals = [a.signal for a in analyses]
            if all(s == "bullish" for s in signals):
                confidence = min(avg + 0.15, 0.95)
            elif all(s == "bearish" for s in signals):
                confidence = min(avg + 0.15, 0.95)
            else:
                confidence = avg * 0.8

        state.analyses.setdefault(symbol, []).append(Analysis(
            agent="researcher",
            symbol=symbol,
            signal=signal,
            confidence=round(confidence, 3),
            reasoning=response[:500],
        ))
    return state
