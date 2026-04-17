from __future__ import annotations

import pytest

from agents.python import relative_strength as rs


def _candles(values: list[float]) -> list[dict]:
    return [
        {"timestamp": 1700000000 + i * 86400, "open": v, "high": v + 1, "low": v - 1, "close": v, "volume": 1_000_000}
        for i, v in enumerate(values)
    ]


@pytest.fixture(autouse=True)
def _reset_cache():
    rs.reset_cache()
    yield
    rs.reset_cache()


def test_compute_return_none_on_short_series():
    assert rs._compute_return(_candles([100, 105]), lookback=20) is None


def test_compute_return_positive():
    candles = _candles([100 + i * 0.5 for i in range(30)])
    r = rs._compute_return(candles, lookback=20)
    assert r is not None
    assert r > 0


def test_ranked_orders_by_return(monkeypatch):
    data = {
        "A": _candles([100 + i * 0.1 for i in range(30)]),
        "B": _candles([100 + i * 0.5 for i in range(30)]),
        "C": _candles([100 - i * 0.2 for i in range(30)]),
    }
    monkeypatch.setattr(rs, "fetch_candles", lambda s, period="3mo", interval="1d": data.get(s, []))

    result = rs.ranked(["A", "B", "C"], lookback_days=20)
    assert [r.symbol for r in result] == ["B", "A", "C"]
    assert result[0].rank == 1
    assert result[-1].rank == 3


def test_percentile_top_is_1(monkeypatch):
    data = {s: _candles([100 + i * (ord(s) - 64) * 0.3 for i in range(30)]) for s in "ABCDE"}
    monkeypatch.setattr(rs, "fetch_candles", lambda s, period="3mo", interval="1d": data.get(s, []))

    result = rs.ranked(list("ABCDE"), lookback_days=20)
    assert result[0].percentile == 1.0


def test_rank_for_single_symbol(monkeypatch):
    data = {
        "X": _candles([100 + i for i in range(30)]),
        "Y": _candles([100 for _ in range(30)]),
        "Z": _candles([100 - i * 0.3 for i in range(30)]),
    }
    monkeypatch.setattr(rs, "fetch_candles", lambda s, period="3mo", interval="1d": data.get(s, []))

    rank = rs.rank_for("X", ["Y", "Z"])
    assert rank is not None
    assert rank.rank == 1


def test_cache_hits_second_call(monkeypatch):
    calls = {"n": 0}

    def fake_fetch(s, period="3mo", interval="1d"):
        calls["n"] += 1
        return _candles([100 + i * 0.5 for i in range(30)])

    monkeypatch.setattr(rs, "fetch_candles", fake_fetch)

    rs.ranked(["A"], lookback_days=20)
    first = calls["n"]
    rs.ranked(["A"], lookback_days=20)
    assert calls["n"] == first


def test_rs_vote_buy_for_top_tier(monkeypatch):
    from core.smart_picker import _rs_vote
    from core.state import PipelineState

    data = {s: _candles([100 + i * (ord(s) - 64) * 0.4 for i in range(30)]) for s in "ABCDEF"}
    monkeypatch.setattr(rs, "fetch_candles", lambda s, period="3mo", interval="1d": data.get(s, []))

    state = PipelineState(symbols=list("ABCDEF"))
    vote = _rs_vote("F", state)
    assert vote is not None
    assert vote.action == "buy"


def test_rs_vote_sell_for_bottom_tier(monkeypatch):
    from core.smart_picker import _rs_vote
    from core.state import PipelineState

    data = {s: _candles([100 + i * (ord(s) - 64) * 0.4 for i in range(30)]) for s in "ABCDEF"}
    monkeypatch.setattr(rs, "fetch_candles", lambda s, period="3mo", interval="1d": data.get(s, []))

    state = PipelineState(symbols=list("ABCDEF"))
    vote = _rs_vote("A", state)
    assert vote is not None
    assert vote.action == "sell"


def test_rs_vote_none_for_middle(monkeypatch):
    from core.smart_picker import _rs_vote
    from core.state import PipelineState

    data = {s: _candles([100 + i * (ord(s) - 64) * 0.4 for i in range(30)]) for s in "ABCDE"}
    monkeypatch.setattr(rs, "fetch_candles", lambda s, period="3mo", interval="1d": data.get(s, []))

    state = PipelineState(symbols=list("ABCDE"))
    vote = _rs_vote("C", state)
    assert vote is None
