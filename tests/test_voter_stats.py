from __future__ import annotations

from agents.python import paper_broker
from agents.python.voter_stats import (
    apply_weights_to_votes,
    get_all_stats,
    get_weight,
    parse_voters,
    record_trade_outcome,
    reset_all,
)


class _FakeVote:
    def __init__(self, source: str, confidence: float):
        self.source = source
        self.confidence = confidence


def test_parse_voters_simple():
    s = "[consensus_2/3:bb_mean_reversion] size×0.85 bb_mean_reversion:buy@0.72; momentum:buy@0.68"
    result = parse_voters(s)
    voters = [v[0] for v in result]
    assert "bb_mean_reversion" in voters
    assert "momentum" in voters


def test_parse_voters_empty():
    assert parse_voters("") == []
    assert parse_voters("no votes here") == []


def test_record_trade_outcome_creates_rows():
    reasoning = "bb:buy@0.7; momentum:buy@0.65"
    record_trade_outcome(reasoning, pnl=50.0)
    stats = {s.voter: s for s in get_all_stats()}
    assert "bb" in stats
    assert stats["bb"].wins == 1
    assert stats["bb"].total_pnl == 50.0
    assert "momentum" in stats


def test_record_trade_outcome_accumulates():
    reasoning = "bb:buy@0.7"
    record_trade_outcome(reasoning, pnl=100.0)
    record_trade_outcome(reasoning, pnl=-50.0)
    record_trade_outcome(reasoning, pnl=30.0)
    stats = {s.voter: s for s in get_all_stats()}
    assert stats["bb"].wins == 2
    assert stats["bb"].losses == 1
    assert stats["bb"].total_pnl == 80.0


def test_get_weight_returns_1_below_min_trades():
    record_trade_outcome("bb:buy@0.7", pnl=10)
    assert get_weight("bb", min_trades=5) == 1.0


def test_get_weight_boosts_high_winrate():
    for _ in range(7):
        record_trade_outcome("bb:buy@0.7", pnl=10)
    for _ in range(3):
        record_trade_outcome("bb:buy@0.7", pnl=-5)
    w = get_weight("bb", min_trades=5)
    assert w > 1.0


def test_get_weight_cuts_low_winrate():
    for _ in range(2):
        record_trade_outcome("momentum:buy@0.7", pnl=10)
    for _ in range(8):
        record_trade_outcome("momentum:buy@0.7", pnl=-5)
    w = get_weight("momentum", min_trades=5)
    assert w < 1.0


def test_apply_weights_to_votes_scales_confidence():
    for _ in range(7):
        record_trade_outcome("bb_mean_reversion:buy@0.7", pnl=10)
    for _ in range(3):
        record_trade_outcome("bb_mean_reversion:buy@0.7", pnl=-5)

    votes = [_FakeVote("bb_mean_reversion", 0.7)]
    result = apply_weights_to_votes(votes)
    assert result[0].confidence > 0.7


def test_reset_clears_stats():
    record_trade_outcome("bb:buy@0.7", pnl=10)
    reset_all()
    assert get_all_stats() == []


def test_record_integrated_with_paper_broker(tmp_path, monkeypatch):
    paper_broker.reset_account()
    paper_broker.submit_order("AAPL", 10, "buy", 150.0, reasoning="bb:buy@0.8")
    paper_broker.submit_order("AAPL", 10, "sell", 160.0)
    stats = {s.voter: s for s in get_all_stats()}
    assert "bb" in stats
    assert stats["bb"].wins == 1
