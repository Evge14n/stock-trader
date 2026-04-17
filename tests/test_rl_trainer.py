from __future__ import annotations

import math

import pytest

pytest.importorskip("stable_baselines3")
pytest.importorskip("gymnasium")

from agents.python.rl import env as env_module
from agents.python.rl import trainer
from agents.python.rl.env import EnvConfig, TradingEnv


def _synthetic_candles(n: int = 150, slope: float = 0.4) -> list[dict]:
    rows = []
    base = 100.0
    for i in range(n):
        price = base + i * slope + math.sin(i / 6) * 2
        rows.append(
            {
                "timestamp": 1700000000 + i * 86400,
                "open": price - 0.5,
                "high": price + 1.5,
                "low": price - 1.5,
                "close": price,
                "volume": 1_000_000,
            }
        )
    return rows


@pytest.fixture
def patched_data(monkeypatch):
    def fake_fetch(symbol, period="3mo", interval="1d"):
        slope = 0.4 if symbol == "AAA" else 0.2
        return _synthetic_candles(n=160, slope=slope)

    monkeypatch.setattr(trainer, "fetch_candles", fake_fetch)


def test_load_historical_returns_dict(patched_data):
    data = trainer.load_historical(["AAA", "BBB"], period="6mo")
    assert "AAA" in data
    assert "BBB" in data
    assert len(data["AAA"]) > 100


def test_build_vec_env_creates_envs(patched_data):
    data = trainer.load_historical(["AAA"], period="6mo")
    vec = trainer.build_vec_env(data)
    assert vec.num_envs == 1
    obs = vec.reset()
    assert obs.shape == (1, 13)


def test_train_produces_checkpoint(tmp_path, monkeypatch, patched_data):
    monkeypatch.setattr(trainer, "_rl_dir", lambda: tmp_path)
    cfg = trainer.TrainConfig(
        symbols=["AAA"],
        period="6mo",
        total_timesteps=256,
        n_steps=64,
        batch_size=32,
    )
    path = trainer.train(cfg)
    assert path.exists()
    assert (tmp_path / "ppo_latest.zip").exists()
    assert (tmp_path / "ppo_latest.json").exists()


def test_load_latest_and_evaluate(tmp_path, monkeypatch, patched_data):
    monkeypatch.setattr(trainer, "_rl_dir", lambda: tmp_path)
    cfg = trainer.TrainConfig(
        symbols=["AAA"],
        period="6mo",
        total_timesteps=256,
        n_steps=64,
        batch_size=32,
    )
    trainer.train(cfg)

    model = trainer.load_latest(tmp_path)
    assert model is not None

    data = trainer.load_historical(["AAA"], period="6mo")
    results = trainer.evaluate(model, data)
    assert "AAA" in results
    assert "final_equity" in results["AAA"]


def test_env_module_exposes_gym_flag():
    import pandas as pd

    df = pd.DataFrame(_synthetic_candles())
    env = TradingEnv(df, EnvConfig())
    assert env is not None
    assert hasattr(env_module, "_GYM_AVAILABLE")
