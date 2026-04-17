from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd
import structlog

from agents.python.data_collector import fetch_candles
from agents.python.indicators import _to_df
from agents.python.rl.env import EnvConfig, TradingEnv
from config.settings import settings

log = structlog.get_logger(__name__)


@dataclass
class TrainConfig:
    symbols: list[str]
    period: str = "2y"
    total_timesteps: int = 50_000
    learning_rate: float = 3e-4
    n_steps: int = 512
    batch_size: int = 64
    gamma: float = 0.99
    seed: int = 42
    model_dir: str = "data/rl"


def _rl_dir() -> Path:
    p = settings.data_dir / "rl"
    p.mkdir(parents=True, exist_ok=True)
    return p


def load_historical(symbols: list[str], period: str) -> dict[str, pd.DataFrame]:
    out: dict[str, pd.DataFrame] = {}
    for sym in symbols:
        candles = fetch_candles(sym, period=period)
        if not candles:
            log.warning("no_candles", symbol=sym)
            continue
        df = _to_df(candles)
        if len(df) > 40:
            out[sym] = df
    return out


def build_vec_env(data: dict[str, pd.DataFrame], env_config: EnvConfig | None = None):
    from stable_baselines3.common.vec_env import DummyVecEnv

    env_config = env_config or EnvConfig()
    fns = []
    for sym, df in data.items():
        frozen_df = df
        frozen_cfg = env_config

        def _make(d=frozen_df, c=frozen_cfg):
            return TradingEnv(d, c)

        _make.__name__ = f"env_{sym}"
        fns.append(_make)

    if not fns:
        raise ValueError("no symbols with valid data")
    return DummyVecEnv(fns)


def train(config: TrainConfig) -> Path:
    from stable_baselines3 import PPO

    data = load_historical(config.symbols, config.period)
    if not data:
        raise RuntimeError("no training data available")

    vec_env = build_vec_env(data)
    model = PPO(
        "MlpPolicy",
        vec_env,
        learning_rate=config.learning_rate,
        n_steps=config.n_steps,
        batch_size=config.batch_size,
        gamma=config.gamma,
        seed=config.seed,
        verbose=0,
    )

    log.info(
        "train_start",
        symbols=list(data.keys()),
        timesteps=config.total_timesteps,
        device=str(model.device),
    )
    model.learn(total_timesteps=config.total_timesteps, progress_bar=False)

    ts = datetime.now().strftime("%Y%m%dT%H%M%S")
    out_dir = _rl_dir()
    versioned = out_dir / f"ppo_{ts}.zip"
    latest = out_dir / "ppo_latest.zip"
    model.save(str(versioned))
    model.save(str(latest))

    meta = {
        "timestamp": ts,
        "symbols": list(data.keys()),
        "config": asdict(config),
        "device": str(model.device),
    }
    (out_dir / "ppo_latest.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    log.info("train_done", path=str(versioned), latest=str(latest))
    return versioned


def load_latest(model_dir: str | Path | None = None):
    from stable_baselines3 import PPO

    path = Path(model_dir) if model_dir else _rl_dir()
    latest = path / "ppo_latest.zip" if path.is_dir() else path
    if not latest.exists():
        return None
    return PPO.load(str(latest))


def evaluate(model, data: dict[str, pd.DataFrame]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for sym, df in data.items():
        env = TradingEnv(df, EnvConfig())
        obs, _ = env.reset(seed=0)
        done = False
        while not done:
            action, _ = model.predict(obs, deterministic=True)
            obs, _, done, _, _ = env.step(int(action))
        out[sym] = env.summary()
    return out
