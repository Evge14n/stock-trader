from __future__ import annotations

from core.state import PipelineState


def scan_opportunities(state: PipelineState) -> list[str]:
    scored = {}

    for symbol in state.symbols:
        indicators = state.indicators.get(symbol, [])
        if not indicators:
            continue

        score = 0

        rsi = next((i for i in indicators if i.name == "RSI"), None)
        if rsi:
            if rsi.signal == "oversold":
                score += 2
            elif rsi.signal == "overbought":
                score -= 1

        bb = next((i for i in indicators if i.name == "BB"), None)
        if bb:
            if bb.signal == "oversold":
                score += 2
            elif bb.signal == "overbought":
                score -= 1

        macd = next((i for i in indicators if i.name == "MACD"), None)
        if macd:
            if macd.signal == "bullish":
                score += 1
            elif macd.signal == "bearish":
                score -= 1

        adx = next((i for i in indicators if i.name == "ADX"), None)
        if adx and adx.signal == "trending":
            score += 1

        vwap = next((i for i in indicators if i.name == "VWAP"), None)
        if vwap and vwap.signal == "above":
            score += 1

        sma50 = next((i for i in indicators if i.name == "SMA50"), None)
        if sma50 and sma50.signal == "above":
            score += 1

        sma200 = next((i for i in indicators if i.name == "SMA200"), None)
        if sma200 and sma200.signal == "golden":
            score += 2

        scored[symbol] = score

    ranked = sorted(scored.items(), key=lambda x: x[1], reverse=True)
    return [sym for sym, sc in ranked if sc >= 2]


async def filter_watchlist(state: PipelineState) -> PipelineState:
    opportunities = scan_opportunities(state)
    if opportunities:
        state.symbols = opportunities
    return state
