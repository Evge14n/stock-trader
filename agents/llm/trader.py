from __future__ import annotations

import asyncio

from config.settings import settings
from core import llm_client
from core.state import PipelineState, TradeSignal

SYSTEM = """You are a disciplined swing trader. Based on the research synthesis, decide whether to trade.
If you decide to trade, output:
- action: "buy" or "sell"
- stop_loss_pct: percentage for stop loss (e.g. 0.03 for 3%)
- take_profit_pct: percentage for take profit (e.g. 0.06 for 6%)
- reasoning: one sentence

If no trade, output: action: "pass" with reasoning.
Risk management rules: never risk more than 2% per trade. Minimum 2:1 reward-to-risk ratio.
Only trade when confidence > 0.65 and signals align."""


def _build_prompt(symbol: str, state: PipelineState) -> str:
    analyses = state.analyses.get(symbol, [])
    md = state.market_data.get(symbol)

    researcher_analysis = None
    for a in reversed(analyses):
        if a.agent == "researcher":
            researcher_analysis = a
            break

    lines = [f"Symbol: {symbol}"]
    if md:
        lines.append(f"Price: ${md.price}")

    if researcher_analysis:
        lines.append(f"\nResearch signal: {researcher_analysis.signal}")
        lines.append(f"Confidence: {researcher_analysis.confidence}")
        lines.append(f"Reasoning: {researcher_analysis.reasoning[:300]}")

    indicators = state.indicators.get(symbol, [])
    atr = next((i for i in indicators if i.name == "ATR"), None)
    if atr and md:
        lines.append(f"\nATR: {atr.value} ({round(atr.value / md.price * 100, 2)}% of price)")

    lines.append(f"\nMax position size: ${settings.max_position_size}")
    lines.append(f"Risk per trade: {settings.risk_per_trade * 100}%")

    return "\n".join(lines)


def _calc_quantity(price: float, stop_pct: float) -> int:
    if price <= 0 or stop_pct <= 0:
        return 0
    risk_amount = settings.max_position_size * settings.risk_per_trade
    risk_per_share = price * stop_pct
    qty = int(risk_amount / risk_per_share)
    max_shares = int(settings.max_position_size / price)
    return min(qty, max_shares)


async def _decide_one(symbol: str, state: PipelineState) -> TradeSignal | None:
    analyses = state.analyses.get(symbol, [])
    researcher = None
    for a in reversed(analyses):
        if a.agent == "researcher":
            researcher = a
            break

    if not researcher or researcher.confidence < 0.55:
        return None

    if researcher.signal == "hold":
        return None

    prompt = _build_prompt(symbol, state)
    response = await llm_client.query(prompt, system=SYSTEM, temperature=0.1)
    resp_lower = response.lower()

    if "pass" in resp_lower and "buy" not in resp_lower and "sell" not in resp_lower:
        return None

    action = "buy" if "buy" in resp_lower else "sell" if "sell" in resp_lower else None
    if not action:
        return None

    md = state.market_data.get(symbol)
    if not md or md.price <= 0:
        return None

    stop_pct = 0.03
    tp_pct = 0.06
    for pct in [0.02, 0.03, 0.04, 0.05]:
        if str(pct) in response:
            stop_pct = pct
            tp_pct = pct * 2
            break

    qty = _calc_quantity(md.price, stop_pct)
    if qty <= 0:
        return None

    sl = round(md.price * (1 - stop_pct), 2) if action == "buy" else round(md.price * (1 + stop_pct), 2)
    tp = round(md.price * (1 + tp_pct), 2) if action == "buy" else round(md.price * (1 - tp_pct), 2)

    return TradeSignal(
        symbol=symbol,
        action=action,
        quantity=qty,
        entry_price=md.price,
        stop_loss=sl,
        take_profit=tp,
        confidence=researcher.confidence,
        reasoning=response[:300],
    )


async def decide(state: PipelineState) -> PipelineState:
    results = await asyncio.gather(*[_decide_one(s, state) for s in state.symbols])
    for signal in results:
        if signal:
            state.signals.append(signal)
    return state
