from __future__ import annotations

import pytest

from agents.python import correlation_sizing


@pytest.fixture(autouse=True)
def _reset():
    correlation_sizing.reset_cache()
    yield
    correlation_sizing.reset_cache()


def _stub_matrix(corr_map: dict) -> dict:
    symbols = sorted({s for pair in corr_map for s in pair})
    matrix = {s: {s: 1.0} for s in symbols}
    for (a, b), v in corr_map.items():
        matrix.setdefault(a, {})[b] = v
        matrix.setdefault(b, {})[a] = v
    for s1 in symbols:
        for s2 in symbols:
            matrix[s1].setdefault(s2, 0.0)
    return {"matrix": matrix, "symbols": symbols}


def test_max_correlation_empty_positions():
    assert correlation_sizing.max_correlation("AAPL", []) == 0.0


def test_max_correlation_ignores_self():
    assert correlation_sizing.max_correlation("AAPL", ["AAPL"]) == 0.0


def test_max_correlation_picks_highest_abs(monkeypatch):
    stub = _stub_matrix({("AAPL", "MSFT"): 0.85, ("AAPL", "KO"): 0.12})
    monkeypatch.setattr(correlation_sizing, "_cached_matrix", lambda syms, period="3mo": stub)

    result = correlation_sizing.max_correlation("AAPL", ["MSFT", "KO"])
    assert result == 0.85


def test_size_factor_below_threshold_returns_1(monkeypatch):
    stub = _stub_matrix({("AAPL", "XOM"): 0.3})
    monkeypatch.setattr(correlation_sizing, "_cached_matrix", lambda syms, period="3mo": stub)

    factor, corr = correlation_sizing.size_factor("AAPL", ["XOM"], threshold=0.7, max_cut=0.5)
    assert factor == 1.0
    assert corr == 0.3


def test_size_factor_scales_down_above_threshold(monkeypatch):
    stub = _stub_matrix({("AAPL", "MSFT"): 0.9})
    monkeypatch.setattr(correlation_sizing, "_cached_matrix", lambda syms, period="3mo": stub)

    factor, corr = correlation_sizing.size_factor("AAPL", ["MSFT"], threshold=0.7, max_cut=0.5)
    assert 0.5 <= factor < 1.0
    assert corr == 0.9


def test_size_factor_clamps_to_max_cut(monkeypatch):
    stub = _stub_matrix({("AAPL", "MSFT"): 1.0})
    monkeypatch.setattr(correlation_sizing, "_cached_matrix", lambda syms, period="3mo": stub)

    factor, _ = correlation_sizing.size_factor("AAPL", ["MSFT"], threshold=0.7, max_cut=0.4)
    assert factor == 0.4


def test_cache_reuses_within_ttl(monkeypatch):
    calls = {"n": 0}

    def fake_compute(symbols, period="3mo"):
        calls["n"] += 1
        return _stub_matrix({("A", "B"): 0.5})

    monkeypatch.setattr(correlation_sizing, "compute_correlation_matrix", fake_compute)

    correlation_sizing._cached_matrix(["A", "B"])
    correlation_sizing._cached_matrix(["A", "B"])
    correlation_sizing._cached_matrix(["A", "B"])
    assert calls["n"] == 1


def test_size_factor_negative_correlation_also_caps(monkeypatch):
    stub = _stub_matrix({("AAPL", "GLD"): -0.85})
    monkeypatch.setattr(correlation_sizing, "_cached_matrix", lambda syms, period="3mo": stub)

    factor, corr = correlation_sizing.size_factor("AAPL", ["GLD"], threshold=0.7, max_cut=0.5)
    assert factor < 1.0
    assert corr == 0.85
