from __future__ import annotations

import math

import pytest

pytest.importorskip("stable_baselines3")
pytest.importorskip("gymnasium")

from agents.python import backtest as bt_mod
from agents.python.rl import compare


def _candles(n: int = 250, slope: float = 0.25) -> list[dict]:
    rows = []
    base = 100.0
    for i in range(n):
        price = base + i * slope + math.sin(i / 8) * 3
        rows.append(
            {
                "timestamp": 1700000000 + i * 86400,
                "open": price - 0.3,
                "high": price + 1.1,
                "low": price - 1.1,
                "close": price,
                "volume": 1_000_000,
            }
        )
    return rows


@pytest.fixture
def patched(monkeypatch):
    monkeypatch.setattr(compare, "fetch_candles", lambda s, period="3mo", interval="1d": _candles())
    monkeypatch.setattr(bt_mod, "fetch_candles", lambda s, period="3mo", interval="1d": _candles())


def test_strategy_result_summary_formats():
    r = compare.StrategyResult(name="x", total_pnl=100.0, total_pnl_pct=1.0, trades=5, wins=3, win_rate=0.6)
    s = r.summary()
    assert s["name"] == "x"
    assert s["total_pnl"] == 100.0
    assert s["win_rate"] == 60.0


def test_run_ab_produces_report(patched):
    report = compare.run_ab(
        symbols=["AAA"],
        period="2y",
        train_ratio=0.7,
        timesteps=256,
        initial=10_000.0,
    )
    assert "AAA" in report.symbols
    assert report.winner in ("rl_ppo", "bb_mean_reversion", "tie")
    s = report.summary()
    assert "rl" in s
    assert "bb" in s
    assert "delta_pnl_pct" in s


def test_run_ab_handles_no_data(monkeypatch):
    monkeypatch.setattr(compare, "fetch_candles", lambda *a, **kw: [])
    monkeypatch.setattr(bt_mod, "fetch_candles", lambda *a, **kw: [])

    report = compare.run_ab(
        symbols=["NONE"],
        period="2y",
        train_ratio=0.7,
        timesteps=128,
        initial=10_000.0,
    )
    assert report.rl.trades == 0
    assert report.bb.trades == 0
    assert report.winner == "tie"
