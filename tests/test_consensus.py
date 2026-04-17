from __future__ import annotations

from agents.python.consensus import (
    compute_consensus,
    regime_ok_for_mean_reversion,
    regime_ok_for_momentum,
)
from core.state import Analysis


def _a(agent: str, signal: str, conf: float = 0.7) -> Analysis:
    return Analysis(agent=agent, signal=signal, confidence=conf, reasoning="")


def test_consensus_empty():
    r = compute_consensus([])
    assert r.total == 0
    assert r.direction == "mixed"
    assert not r.passes(4, 0.6)


def test_consensus_all_bullish():
    analyses = [
        _a("technical", "bullish"),
        _a("news", "bullish"),
        _a("sector", "bullish"),
        _a("fundamental", "bullish"),
        _a("momentum", "bullish"),
        _a("volatility", "bullish"),
    ]
    r = compute_consensus(analyses)
    assert r.direction == "bullish"
    assert r.bullish == 6
    assert r.alignment_pct == 1.0
    assert r.passes(4, 0.6)


def test_consensus_mixed_does_not_pass():
    analyses = [
        _a("technical", "bullish"),
        _a("news", "bearish"),
        _a("sector", "neutral"),
        _a("fundamental", "bullish"),
        _a("momentum", "bearish"),
        _a("volatility", "neutral"),
    ]
    r = compute_consensus(analyses)
    assert r.direction == "mixed"
    assert not r.passes(4, 0.6)


def test_consensus_respects_min_agents():
    analyses = [
        _a("technical", "bullish"),
        _a("news", "bullish"),
        _a("sector", "bullish"),
    ]
    r = compute_consensus(analyses)
    assert r.direction == "bullish"
    assert r.bullish == 3
    assert not r.passes(4, 0.5)
    assert r.passes(3, 0.5)


def test_consensus_ignores_non_voting_agents():
    analyses = [
        _a("researcher", "bullish"),
        _a("trader", "bullish"),
        _a("technical", "bearish"),
    ]
    r = compute_consensus(analyses)
    assert r.total == 1
    assert r.bearish == 1


def test_normalize_buy_signal_maps_to_bullish():
    analyses = [_a("technical", "buy"), _a("news", "strong_buy")]
    r = compute_consensus(analyses)
    assert r.bullish == 2


def test_regime_filters():
    assert regime_ok_for_mean_reversion(20) is True
    assert regime_ok_for_mean_reversion(35) is False
    assert regime_ok_for_momentum(30) is True
    assert regime_ok_for_momentum(15) is False
