from __future__ import annotations

from core.state import Analysis, PipelineState, TradeSignal

AGENT_WEIGHTS = {
    "technical_analyst": 0.20,
    "fundamental_analyst": 0.20,
    "momentum_analyst": 0.15,
    "news_analyst": 0.15,
    "sector_tech": 0.10,
    "sector_finance": 0.10,
    "sector_healthcare": 0.10,
    "sector_energy": 0.10,
    "sector_consumer": 0.10,
    "sector_unknown": 0.05,
    "volatility_analyst": 0.10,
    "researcher": 0.20,
}


def _signal_numeric(signal: str) -> float:
    mapping = {
        "strong_buy": 1.0,
        "buy": 0.7,
        "bullish": 0.7,
        "neutral": 0.0,
        "hold": 0.0,
        "sell": -0.7,
        "bearish": -0.7,
        "strong_sell": -1.0,
    }
    return mapping.get(signal.lower(), 0.0)


def explain_decision(symbol: str, state: PipelineState) -> dict:
    analyses = state.analyses.get(symbol, [])
    if not analyses:
        return {"symbol": symbol, "decision": "no_data", "contributions": []}

    contributions = []
    total_weighted_signal = 0.0
    total_weight = 0.0

    for a in analyses:
        weight = AGENT_WEIGHTS.get(a.agent, 0.10)
        numeric = _signal_numeric(a.signal)
        weighted = weight * numeric * a.confidence

        contributions.append(
            {
                "agent": a.agent,
                "signal": a.signal,
                "confidence": round(a.confidence, 3),
                "weight": round(weight, 3),
                "contribution": round(weighted, 4),
                "reasoning": a.reasoning[:300],
            }
        )
        total_weighted_signal += weighted
        total_weight += weight * a.confidence

    final_score = total_weighted_signal / total_weight if total_weight else 0.0

    if final_score > 0.3:
        decision = "buy"
    elif final_score < -0.3:
        decision = "sell"
    else:
        decision = "hold"

    matching_signal = next((s for s in state.signals if s.symbol == symbol), None)
    executed = matching_signal is not None

    drivers = sorted(contributions, key=lambda c: abs(c["contribution"]), reverse=True)[:3]

    return {
        "symbol": symbol,
        "decision": decision,
        "final_score": round(final_score, 3),
        "executed": executed,
        "contributions": contributions,
        "top_drivers": drivers,
        "executed_signal": _signal_to_dict(matching_signal) if matching_signal else None,
    }


def _signal_to_dict(sig: TradeSignal) -> dict:
    return {
        "action": sig.action,
        "quantity": sig.quantity,
        "entry_price": sig.entry_price,
        "stop_loss": sig.stop_loss,
        "take_profit": sig.take_profit,
        "confidence": round(sig.confidence, 3),
    }


def explain_all(state: PipelineState) -> list[dict]:
    return [explain_decision(sym, state) for sym in state.symbols]


def counterfactual(symbol: str, state: PipelineState, flip_agent: str) -> dict:
    analyses = state.analyses.get(symbol, [])
    if not analyses:
        return {"symbol": symbol, "error": "no analyses"}

    flipped = []
    for a in analyses:
        if a.agent == flip_agent:
            new_signal = "bearish" if a.signal in ("bullish", "buy", "strong_buy") else "bullish"
            flipped.append(
                Analysis(
                    agent=a.agent,
                    symbol=a.symbol,
                    signal=new_signal,
                    confidence=a.confidence,
                    reasoning=a.reasoning,
                )
            )
        else:
            flipped.append(a)

    total = 0.0
    total_w = 0.0
    for a in flipped:
        w = AGENT_WEIGHTS.get(a.agent, 0.10)
        total += w * _signal_numeric(a.signal) * a.confidence
        total_w += w * a.confidence

    score = total / total_w if total_w else 0.0
    decision = "buy" if score > 0.3 else "sell" if score < -0.3 else "hold"

    return {
        "symbol": symbol,
        "flipped_agent": flip_agent,
        "new_decision": decision,
        "new_score": round(score, 3),
    }
