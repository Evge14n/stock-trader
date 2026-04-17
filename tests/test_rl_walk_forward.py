from __future__ import annotations

import math

import pytest

pytest.importorskip("stable_baselines3")
pytest.importorskip("gymnasium")

from agents.python.rl import walk_forward as wf


def _candles(n: int = 400, slope: float = 0.25) -> list[dict]:
    rows = []
    base = 100.0
    for i in range(n):
        price = base + i * slope + math.sin(i / 9) * 3
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


@pytest.fixture
def patched(monkeypatch):
    def fake_fetch(symbol, period="3mo", interval="1d"):
        return _candles(n=420, slope=0.3 if symbol == "AAA" else 0.2)

    monkeypatch.setattr(wf, "fetch_candles", fake_fetch)


def test_split_indices_empty_when_short():
    assert wf._split_indices(50, 180, 60, 60) == []


def test_split_indices_produces_windows():
    out = wf._split_indices(400, 180, 60, 60)
    assert len(out) >= 3
    first = out[0]
    assert first[1] - first[0] == 180
    assert first[3] - first[2] == 60


def test_load_per_symbol_filters_short_series(patched):
    data = wf._load_per_symbol(["AAA", "BBB"], period="2y")
    assert "AAA" in data
    assert "BBB" in data


def test_run_rl_walk_forward_produces_report(patched):
    report = wf.run_rl_walk_forward(
        symbols=["AAA"],
        period="2y",
        train_bars=150,
        test_bars=50,
        step_bars=50,
        timesteps=256,
    )
    assert len(report.windows) >= 1
    s = report.summary()
    assert s["windows"] == len(report.windows)
    assert "combined_test_pnl" in s
    assert 0.0 <= s["consistency_pct"] <= 100.0


def test_empty_on_missing_data(monkeypatch):
    monkeypatch.setattr(wf, "fetch_candles", lambda *a, **kw: [])
    report = wf.run_rl_walk_forward(
        symbols=["NONE"],
        period="2y",
        train_bars=100,
        test_bars=30,
        step_bars=30,
        timesteps=128,
    )
    assert report.windows == []
    assert report.summary()["windows"] == 0
