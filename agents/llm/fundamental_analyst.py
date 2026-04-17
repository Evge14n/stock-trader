from __future__ import annotations

import asyncio

import yfinance as yf

from core import llm_client
from core.state import Analysis, PipelineState

SYSTEM = """You are a fundamental equity analyst. Analyze P/E, EPS, revenue growth, and profit margins.
Output:
- signal: bullish, bearish, or neutral
- confidence: 0.0-1.0
- reasoning: one paragraph on valuation and growth quality
Compare against sector norms where possible."""


def _fetch_fundamentals(symbol: str) -> dict:
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info or {}
        return {
            "market_cap": info.get("marketCap"),
            "pe_ratio": info.get("trailingPE"),
            "forward_pe": info.get("forwardPE"),
            "peg_ratio": info.get("pegRatio"),
            "eps": info.get("trailingEps"),
            "revenue_growth": info.get("revenueGrowth"),
            "profit_margin": info.get("profitMargins"),
            "roe": info.get("returnOnEquity"),
            "debt_to_equity": info.get("debtToEquity"),
            "dividend_yield": info.get("dividendYield"),
            "sector": info.get("sector", ""),
            "industry": info.get("industry", ""),
            "target_mean_price": info.get("targetMeanPrice"),
            "recommendation": info.get("recommendationKey", ""),
        }
    except Exception:
        return {}


def _build_prompt(symbol: str, data: dict, price: float) -> str:
    if not data:
        return f"No fundamental data available for {symbol}. Return neutral."

    target = data.get("target_mean_price")
    upside = ""
    if target and price:
        diff_pct = (target - price) / price * 100
        upside = f"\nAnalyst target: ${target:.2f} ({diff_pct:+.1f}% vs current)"

    lines = [
        f"Symbol: {symbol}",
        f"Sector: {data.get('sector', 'n/a')} / {data.get('industry', 'n/a')}",
        f"Market cap: ${(data.get('market_cap') or 0) / 1e9:.1f}B",
        f"P/E: {data.get('pe_ratio', 'n/a')}",
        f"Forward P/E: {data.get('forward_pe', 'n/a')}",
        f"PEG: {data.get('peg_ratio', 'n/a')}",
        f"EPS: {data.get('eps', 'n/a')}",
        f"Revenue growth: {(data.get('revenue_growth') or 0) * 100:.1f}%",
        f"Profit margin: {(data.get('profit_margin') or 0) * 100:.1f}%",
        f"ROE: {(data.get('roe') or 0) * 100:.1f}%",
        f"Analyst rating: {data.get('recommendation', 'n/a')}",
    ]
    if upside:
        lines.append(upside)
    return "\n".join(lines)


async def _analyze_one(symbol: str, state: PipelineState) -> Analysis | None:
    md = state.market_data.get(symbol)
    if not md:
        return None

    try:
        data = await asyncio.to_thread(_fetch_fundamentals, symbol)
    except Exception as e:
        state.add_error(f"fundamental_analyst [{symbol}]: {e}")
        return None

    prompt = _build_prompt(symbol, data, md.price)
    response = await llm_client.query(prompt, system=SYSTEM)

    signal = "neutral"
    for s in ["bullish", "bearish", "neutral"]:
        if s in response.lower():
            signal = s
            break

    confidence = 0.5
    pe = data.get("pe_ratio") or 0
    if 0 < pe < 15:
        confidence += 0.15
    elif pe > 40:
        confidence -= 0.1

    rec = (data.get("recommendation") or "").lower()
    if "buy" in rec or "strong_buy" in rec:
        confidence += 0.1
    elif "sell" in rec:
        confidence -= 0.15

    confidence = max(0.2, min(0.9, confidence))

    return Analysis(
        agent="fundamental_analyst",
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
