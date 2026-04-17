from __future__ import annotations

import asyncio
import math

import pytest

pytest.importorskip("stable_baselines3")
pytest.importorskip("gymnasium")

from agents.python.rl import agent as rl_agent
from agents.python.rl import trainer
from core.state import MarketData, PipelineState


def _candles(n: int = 120, slope: float = 0.4) -> list[dict]:
    rows = []
    base = 100.0
    for i in range(n):
        price = base + i * slope + math.sin(i / 5) * 2
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


@pytest.fixture(autouse=True)
def _reset_agent_cache():
    rl_agent.reset_cache()
    yield
    rl_agent.reset_cache()


@pytest.fixture
def rl_model_path(tmp_path, monkeypatch):
    rl_dir = tmp_path / "rl"
    rl_dir.mkdir()
    monkeypatch.setattr(rl_agent, "_rl_model_path", lambda: rl_dir / "ppo_latest.zip")
    monkeypatch.setattr(trainer, "_rl_dir", lambda: rl_dir)
    monkeypatch.setattr(trainer, "fetch_candles", lambda s, period="3mo", interval="1d": _candles())
    cfg = trainer.TrainConfig(
        symbols=["TEST"],
        period="6mo",
        total_timesteps=256,
        n_steps=64,
        batch_size=32,
    )
    trainer.train(cfg)
    return rl_dir / "ppo_latest.zip"


def test_decide_without_model_records_error(monkeypatch, tmp_path):
    monkeypatch.setattr(rl_agent, "_rl_model_path", lambda: tmp_path / "missing.zip")
    state = PipelineState(symbols=["AAPL"])
    asyncio.run(rl_agent.decide(state))
    assert any("no model" in e for e in state.errors)
    assert state.signals == []


def test_decide_with_model_no_ohlcv_adds_nothing(rl_model_path):
    state = PipelineState(symbols=["AAPL"])
    state.market_data["AAPL"] = MarketData(symbol="AAPL", price=100.0, ohlcv=[])
    asyncio.run(rl_agent.decide(state))
    assert state.signals == []


def test_decide_with_model_and_ohlcv_runs_predict(rl_model_path):
    state = PipelineState(symbols=["AAPL"])
    candles = _candles()
    state.market_data["AAPL"] = MarketData(
        symbol="AAPL",
        price=candles[-1]["close"],
        ohlcv=candles,
    )
    asyncio.run(rl_agent.decide(state))
    for s in state.signals:
        assert s.symbol == "AAPL"
        assert s.action in ("buy", "sell")
        assert s.quantity > 0


def test_is_available_returns_false_without_model(monkeypatch, tmp_path):
    monkeypatch.setattr(rl_agent, "_rl_model_path", lambda: tmp_path / "missing.zip")
    assert rl_agent.is_available() is False


def test_resolve_decide_respects_flag(monkeypatch):
    from agents.llm.trader import decide as llm_decide
    from config.settings import settings
    from core.orchestrator import _resolve_decide

    monkeypatch.setattr(settings, "use_smart_picker", False)
    monkeypatch.setattr(settings, "use_rl_decision", False)
    assert _resolve_decide() is llm_decide

    monkeypatch.setattr(settings, "use_rl_decision", True)
    resolved = _resolve_decide()
    assert resolved is rl_agent.decide
