from __future__ import annotations

from unittest.mock import patch

from core.smart_picker import _forecaster_vote
from core.state import MarketData, PipelineState


def _fake_state(symbol: str = "X", price: float = 100.0) -> PipelineState:
    state = PipelineState(symbols=[symbol])
    state.market_data[symbol] = MarketData(symbol=symbol, price=price, ohlcv=[{"close": price}])
    return state


def test_forecaster_vote_none_when_no_model(tmp_path, monkeypatch):
    from agents.python import forecaster

    monkeypatch.setattr(forecaster, "_model_path", lambda sym: tmp_path / f"{sym}.json")
    state = _fake_state("X")
    assert _forecaster_vote("X", state) is None


def test_forecaster_vote_buy_on_positive_prediction(tmp_path, monkeypatch):
    from agents.python import forecaster

    model_file = tmp_path / "X.json"
    model_file.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(forecaster, "_model_path", lambda sym: model_file)

    fake_pred = {"predicted_return_pct": 2.5, "model_accuracy": 0.62}
    with patch("agents.python.forecaster.predict_next_return", return_value=fake_pred):
        state = _fake_state("X")
        vote = _forecaster_vote("X", state)

    assert vote is not None
    assert vote.action == "buy"
    assert vote.source == "forecaster_mlp"
    assert vote.confidence > 0.6


def test_forecaster_vote_sell_on_negative_prediction(tmp_path, monkeypatch):
    from agents.python import forecaster

    model_file = tmp_path / "X.json"
    model_file.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(forecaster, "_model_path", lambda sym: model_file)

    fake_pred = {"predicted_return_pct": -2.0, "model_accuracy": 0.58}
    with patch("agents.python.forecaster.predict_next_return", return_value=fake_pred):
        state = _fake_state("X")
        vote = _forecaster_vote("X", state)

    assert vote is not None
    assert vote.action == "sell"


def test_forecaster_vote_none_on_weak_magnitude(tmp_path, monkeypatch):
    from agents.python import forecaster

    model_file = tmp_path / "X.json"
    model_file.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(forecaster, "_model_path", lambda sym: model_file)

    fake_pred = {"predicted_return_pct": 0.3, "model_accuracy": 0.6}
    with patch("agents.python.forecaster.predict_next_return", return_value=fake_pred):
        state = _fake_state("X")
        vote = _forecaster_vote("X", state)

    assert vote is None


def test_forecaster_vote_none_on_low_accuracy(tmp_path, monkeypatch):
    from agents.python import forecaster

    model_file = tmp_path / "X.json"
    model_file.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(forecaster, "_model_path", lambda sym: model_file)

    fake_pred = {"predicted_return_pct": 3.0, "model_accuracy": 0.45}
    with patch("agents.python.forecaster.predict_next_return", return_value=fake_pred):
        state = _fake_state("X")
        vote = _forecaster_vote("X", state)

    assert vote is None


def test_forecaster_vote_skips_on_error(tmp_path, monkeypatch):
    from agents.python import forecaster

    model_file = tmp_path / "X.json"
    model_file.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(forecaster, "_model_path", lambda sym: model_file)

    with patch("agents.python.forecaster.predict_next_return", return_value={"error": "no data"}):
        state = _fake_state("X")
        vote = _forecaster_vote("X", state)

    assert vote is None
