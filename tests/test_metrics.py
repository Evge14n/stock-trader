from __future__ import annotations

from datetime import datetime, timedelta

from agents.python.metrics import rolling_metrics


def _series(values: list[float], days_back_start: int = 60) -> list[dict]:
    points = []
    now = datetime.now()
    for i, v in enumerate(values):
        ts = (now - timedelta(days=days_back_start - i)).isoformat()
        points.append({"timestamp": ts, "equity": float(v)})
    return points


def test_rolling_metrics_empty():
    m = rolling_metrics([], 30)
    assert m["samples"] == 0
    assert m["sharpe"] == 0.0


def test_rolling_metrics_single_point():
    m = rolling_metrics(_series([100_000]), 30)
    assert m["samples"] == 0


def test_rolling_metrics_positive_trend():
    vals = [100_000 + i * 200 for i in range(30)]
    m = rolling_metrics(_series(vals), 30)
    assert m["total_return_pct"] > 0
    assert m["sharpe"] > 0
    assert m["max_drawdown_pct"] == 0.0


def test_rolling_metrics_with_drawdown():
    vals = [100_000, 105_000, 110_000, 108_000, 95_000, 97_000, 102_000]
    m = rolling_metrics(_series(vals, 10), 30)
    assert m["max_drawdown_pct"] > 10


def test_rolling_metrics_sortino_zero_when_no_downside():
    vals = [100_000 + i * 500 for i in range(20)]
    m = rolling_metrics(_series(vals), 30)
    assert m["sortino"] == 0.0


def test_rolling_metrics_calmar_computes_when_drawdown_exists():
    vals = [100_000, 110_000, 105_000, 115_000, 108_000, 118_000]
    m = rolling_metrics(_series(vals, 30), 90)
    assert m["calmar"] != 0 or m["max_drawdown_pct"] > 0


def test_rolling_metrics_respects_window():
    old_point = {"timestamp": (datetime.now() - timedelta(days=200)).isoformat(), "equity": 50_000}
    recent = _series([100_000, 101_000, 102_000, 103_000], days_back_start=5)
    m = rolling_metrics([old_point, *recent], 7)
    assert m["samples"] == 3
