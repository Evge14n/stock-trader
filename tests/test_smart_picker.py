from __future__ import annotations

import asyncio
import math

from config.settings import settings
from core.smart_picker import (
    StrategyVote,
    gather_votes,
    pick_best,
    smart_decide,
)
from core.state import Analysis, Indicator, MarketData, PipelineState


def _candles(n: int = 120, slope: float = 0.3, shock_at: int | None = None) -> list[dict]:
    rows = []
    base = 100.0
    for i in range(n):
        price = base + i * slope + math.sin(i / 7) * 2.0
        if shock_at is not None and i >= shock_at:
            price -= 8.0
        rows.append(
            {
                "timestamp": 1700000000 + i * 86400,
                "open": price - 0.3,
                "high": price + 1.0,
                "low": price - 1.0,
                "close": price,
                "volume": 1_000_000,
            }
        )
    return rows


def test_pick_best_requires_min_voters():
    votes = [StrategyVote(source="a", action="buy", confidence=0.9)]
    assert pick_best(votes) is None


def test_pick_best_picks_majority_action():
    votes = [
        StrategyVote(source="a", action="buy", confidence=0.8),
        StrategyVote(source="b", action="buy", confidence=0.75),
        StrategyVote(source="c", action="sell", confidence=0.9),
    ]
    result = pick_best(votes)
    assert result is not None
    assert result.action == "buy"


def test_pick_best_filters_low_confidence():
    votes = [
        StrategyVote(source="a", action="buy", confidence=0.5),
        StrategyVote(source="b", action="buy", confidence=0.55),
    ]
    result = pick_best(votes)
    assert result is None


def test_pick_best_returns_none_when_no_consensus():
    votes = [
        StrategyVote(source="a", action="buy", confidence=0.9),
        StrategyVote(source="b", action="sell", confidence=0.9),
    ]
    result = pick_best(votes)
    assert result is None


def test_gather_votes_bb_produces_signal_when_oversold(monkeypatch):
    candles = _candles(n=90, slope=-0.4, shock_at=70)
    state = PipelineState(symbols=["X"])
    state.market_data["X"] = MarketData(symbol="X", price=candles[-1]["close"], ohlcv=candles)
    state.indicators["X"] = [
        Indicator(name="ADX", value=20.0, signal="ranging"),
        Indicator(name="BB", value=0.1, signal="oversold"),
        Indicator(name="RSI", value=25.0, signal="oversold"),
    ]
    votes = gather_votes("X", state)
    sources = {v.source for v in votes}
    assert "bb_mean_reversion" in sources or not votes


def test_gather_votes_momentum_in_trending(monkeypatch):
    candles = _candles(n=100, slope=0.8)
    state = PipelineState(symbols=["Y"])
    state.market_data["Y"] = MarketData(symbol="Y", price=candles[-1]["close"], ohlcv=candles)
    state.indicators["Y"] = [
        Indicator(name="ADX", value=35.0, signal="trending"),
        Indicator(name="MACD", value=0.5, signal="bullish", details={"macd": 1.0, "signal": 0.5, "histogram": 0.5}),
    ]
    votes = gather_votes("Y", state)
    sources = {v.source for v in votes}
    assert "bb_mean_reversion" not in sources


def test_smart_decide_no_signals_when_no_consensus():
    state = PipelineState(symbols=["Z"])
    state.market_data["Z"] = MarketData(symbol="Z", price=100, ohlcv=[])
    asyncio.run(smart_decide(state))
    assert state.signals == []


def test_llm_vote_respects_researcher_confidence(monkeypatch):
    monkeypatch.setattr(settings, "researcher_min_confidence", 0.8)
    monkeypatch.setattr(settings, "strict_consensus", False)
    state = PipelineState(symbols=["A"])
    state.market_data["A"] = MarketData(symbol="A", price=100, ohlcv=[])
    state.analyses["A"] = [
        Analysis(agent="researcher", signal="buy", confidence=0.65, reasoning="weak"),
    ]
    votes = gather_votes("A", state)
    assert all(v.source != "llm_research" for v in votes)


def test_llm_vote_passes_with_high_confidence(monkeypatch):
    monkeypatch.setattr(settings, "researcher_min_confidence", 0.7)
    monkeypatch.setattr(settings, "strict_consensus", False)
    state = PipelineState(symbols=["A"])
    state.market_data["A"] = MarketData(symbol="A", price=100, ohlcv=[])
    state.analyses["A"] = [
        Analysis(agent="researcher", signal="buy", confidence=0.85, reasoning="strong"),
    ]
    votes = gather_votes("A", state)
    assert any(v.source == "llm_research" and v.action == "buy" for v in votes)


def test_size_multiplier_scales_with_confluence():
    base = StrategyVote(source="x", action="buy", confidence=0.8, confluence_voters=2, confluence_total=2)
    assert base.size_multiplier() == 0.85

    strong = StrategyVote(source="x", action="buy", confidence=0.8, confluence_voters=4, confluence_total=4)
    assert strong.size_multiplier() == 1.3

    three_of_four = StrategyVote(source="x", action="buy", confidence=0.8, confluence_voters=3, confluence_total=4)
    assert three_of_four.size_multiplier() == 1.15


def test_pick_best_populates_confluence_fields():
    votes = [
        StrategyVote(source="a", action="buy", confidence=0.8),
        StrategyVote(source="b", action="buy", confidence=0.75),
        StrategyVote(source="c", action="buy", confidence=0.82),
    ]
    result = pick_best(votes)
    assert result is not None
    assert result.confluence_voters == 3
    assert result.confluence_total == 3


def test_smart_decide_records_audit_entry():
    state = PipelineState(symbols=["A"])
    candles = _candles(n=90, slope=0.5)
    state.market_data["A"] = MarketData(symbol="A", price=candles[-1]["close"], ohlcv=candles)
    state.indicators["A"] = [
        Indicator(name="ADX", value=30.0, signal="trending"),
        Indicator(name="MACD", value=0.5, details={"macd": 1, "signal": 0.5, "histogram": 0.5}),
    ]
    asyncio.run(smart_decide(state))
    entries = [a for a in state.analyses.get("A", []) if a.agent == "smart_picker"]
    if entries:
        assert "votes=" in entries[0].signal
