from __future__ import annotations

import asyncio

from core import llm_client
from core.state import Analysis, PipelineState

SECTORS = {
    "tech": ["AAPL", "MSFT", "GOOGL", "META", "NVDA", "AMD", "INTC", "NFLX", "CRM", "ORCL"],
    "finance": ["JPM", "BAC", "GS", "MS", "V", "MA", "BRK.B", "C", "WFC", "AXP"],
    "healthcare": ["JNJ", "UNH", "PFE", "ABBV", "MRK", "LLY", "TMO", "ABT", "BMY", "AMGN"],
    "energy": ["XOM", "CVX", "COP", "SLB", "EOG", "MPC", "PSX", "VLO", "OXY", "HAL"],
    "consumer_discretionary": ["AMZN", "TSLA", "HD", "MCD", "NKE", "SBUX", "TGT", "DIS"],
    "consumer_staples": ["KO", "PEP", "PG", "WMT", "COST", "CL", "MDLZ"],
    "commodities": ["GLD", "SLV", "USO", "UNG", "DBC", "IAU", "GDX"],
    "crypto": ["BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "ADA-USD", "DOGE-USD"],
}

SYSTEM = """You are a sector analyst. Analyze how the given stock fits within its sector context.
Consider sector rotation, relative strength, and macro trends.
Output:
- signal: "bullish", "bearish", or "neutral"
- confidence: float 0.0-1.0
- reasoning: one paragraph about sector dynamics affecting this stock
Be specific about sector-level factors."""


def _find_sector(symbol: str) -> str:
    for sector, symbols in SECTORS.items():
        if symbol in symbols:
            return sector
    return "unknown"


def _build_prompt(symbol: str, sector: str, state: PipelineState) -> str:
    md = state.market_data.get(symbol)
    indicators = state.indicators.get(symbol, [])

    lines = [f"Symbol: {symbol}", f"Sector: {sector}"]
    if md:
        lines.append(f"Price: ${md.price}")

    peers_in_watchlist = [s for s in state.symbols if s != symbol and s in SECTORS.get(sector, [])]
    if peers_in_watchlist:
        lines.append(f"\nPeers in portfolio: {', '.join(peers_in_watchlist)}")
        for peer in peers_in_watchlist:
            peer_md = state.market_data.get(peer)
            if peer_md:
                lines.append(f"  {peer}: ${peer_md.price}")

    bb = next((i for i in indicators if i.name == "BB"), None)
    rsi = next((i for i in indicators if i.name == "RSI"), None)
    adx = next((i for i in indicators if i.name == "ADX"), None)

    if bb:
        lines.append(f"\nBB position: {bb.value:.2f} ({bb.signal})")
    if rsi:
        lines.append(f"RSI: {rsi.value} ({rsi.signal})")
    if adx:
        lines.append(f"ADX: {adx.value} ({adx.signal})")

    return "\n".join(lines)


async def _analyze_one(symbol: str, state: PipelineState) -> Analysis | None:
    if symbol not in state.market_data:
        return None

    sector = _find_sector(symbol)
    prompt = _build_prompt(symbol, sector, state)
    response = await llm_client.query(prompt, system=SYSTEM)

    signal = "neutral"
    for s in ["bullish", "bearish", "neutral"]:
        if s in response.lower():
            signal = s
            break

    confidence = 0.5
    if sector == "unknown":
        confidence = 0.35

    return Analysis(
        agent=f"sector_{sector}",
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
