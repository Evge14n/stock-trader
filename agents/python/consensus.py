from __future__ import annotations

from dataclasses import dataclass

from core.state import Analysis

BULLISH_SIGNALS = {"bullish", "bull", "buy", "strong_buy", "oversold"}
BEARISH_SIGNALS = {"bearish", "bear", "sell", "strong_sell", "overbought"}
_VOTING_AGENTS = {"technical", "news", "sector", "fundamental", "momentum", "volatility"}


@dataclass
class ConsensusResult:
    direction: str = "mixed"
    bullish: int = 0
    bearish: int = 0
    neutral: int = 0
    total: int = 0
    alignment_pct: float = 0.0
    avg_confidence: float = 0.0

    def passes(self, min_agents: int, min_alignment: float) -> bool:
        if self.direction == "mixed":
            return False
        dominant = self.bullish if self.direction == "bullish" else self.bearish
        return dominant >= min_agents and self.alignment_pct >= min_alignment


def _normalize(signal: str) -> str:
    s = signal.lower().strip()
    if s in BULLISH_SIGNALS:
        return "bullish"
    if s in BEARISH_SIGNALS:
        return "bearish"
    return "neutral"


def compute_consensus(analyses: list[Analysis]) -> ConsensusResult:
    voters = [a for a in analyses if a.agent in _VOTING_AGENTS]
    if not voters:
        return ConsensusResult()

    bullish = 0
    bearish = 0
    neutral = 0
    conf_sum = 0.0
    for a in voters:
        direction = _normalize(a.signal)
        conf_sum += a.confidence
        if direction == "bullish":
            bullish += 1
        elif direction == "bearish":
            bearish += 1
        else:
            neutral += 1

    total = len(voters)
    if bullish > bearish and bullish > neutral:
        direction = "bullish"
    elif bearish > bullish and bearish > neutral:
        direction = "bearish"
    else:
        direction = "mixed"

    dominant = max(bullish, bearish)
    alignment = dominant / total if total else 0.0

    return ConsensusResult(
        direction=direction,
        bullish=bullish,
        bearish=bearish,
        neutral=neutral,
        total=total,
        alignment_pct=round(alignment, 3),
        avg_confidence=round(conf_sum / total, 3) if total else 0.0,
    )


def regime_ok_for_mean_reversion(adx: float) -> bool:
    return adx < 30


def regime_ok_for_momentum(adx: float) -> bool:
    return adx > 22
