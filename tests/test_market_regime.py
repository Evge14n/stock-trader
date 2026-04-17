from __future__ import annotations

from unittest.mock import patch

import pytest

from agents.python import market_regime as mr


@pytest.fixture(autouse=True)
def _reset():
    mr.reset_cache()
    yield
    mr.reset_cache()


class _Snap:
    def __init__(self, vix: float, regime: str):
        self.vix = vix
        self.risk_regime = regime


def test_combine_risk_on_when_breadth_high_vix_low():
    label, buy_mult, sell_mult, _notes = mr._combine(75, 14.0, "risk_on")
    assert label == "risk_on"
    assert buy_mult > 1.0
    assert sell_mult < 1.0


def test_combine_risk_off_when_breadth_low_vix_high():
    label, buy_mult, sell_mult, _notes = mr._combine(20, 30.0, "risk_off")
    assert label == "risk_off"
    assert buy_mult < 1.0
    assert sell_mult > 1.0


def test_combine_neutral():
    label, buy_mult, sell_mult, _notes = mr._combine(55, 20.0, "neutral")
    assert label == "neutral"
    assert buy_mult == 1.0
    assert sell_mult == 1.0


def test_combine_mild_risk_off():
    label, _, _, _ = mr._combine(35, 22.0, "risk_off")
    assert label == "mild_risk_off"


def test_combine_mild_risk_on():
    label, _, _, _ = mr._combine(65, 17.0, "risk_on")
    assert label == "mild_risk_on"


def test_detect_caches(monkeypatch):
    calls = {"n": 0}

    def fake_breadth(symbols):
        calls["n"] += 1
        return 60.0, 6, 10

    monkeypatch.setattr(mr, "_breadth", fake_breadth)
    with patch("agents.python.macro.fetch_macro", return_value=_Snap(18.0, "neutral")):
        mr.detect(["A", "B"])
        mr.detect(["A", "B"])
    assert calls["n"] == 1


def test_apply_regime_buy_boosted_in_risk_on(monkeypatch):
    class _Vote:
        def __init__(self, action, conf):
            self.action = action
            self.confidence = conf

    monkeypatch.setattr(mr, "_breadth", lambda s: (80.0, 8, 10))
    with patch("agents.python.macro.fetch_macro", return_value=_Snap(14.0, "risk_on")):
        votes = [_Vote("buy", 0.6), _Vote("sell", 0.6)]
        mr.apply_regime_to_votes(votes, ["A", "B"])
    assert votes[0].confidence > 0.6
    assert votes[1].confidence < 0.6


def test_apply_regime_sell_boosted_in_risk_off(monkeypatch):
    class _Vote:
        def __init__(self, action, conf):
            self.action = action
            self.confidence = conf

    monkeypatch.setattr(mr, "_breadth", lambda s: (20.0, 2, 10))
    with patch("agents.python.macro.fetch_macro", return_value=_Snap(30.0, "risk_off")):
        votes = [_Vote("buy", 0.6), _Vote("sell", 0.6)]
        mr.apply_regime_to_votes(votes, ["A", "B"])
    assert votes[0].confidence < 0.6
    assert votes[1].confidence > 0.6


def test_apply_regime_handles_empty_symbols():
    class _Vote:
        def __init__(self):
            self.action = "buy"
            self.confidence = 0.5

    votes = [_Vote()]
    mr.apply_regime_to_votes(votes, [])
    assert votes[0].confidence == 0.5
