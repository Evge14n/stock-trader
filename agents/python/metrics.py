from __future__ import annotations

import math
from datetime import datetime, timedelta

from agents.python import paper_broker

TRADING_DAYS_PER_YEAR = 252


def _returns_from_equity(points: list[dict]) -> list[float]:
    if len(points) < 2:
        return []
    returns = []
    for i in range(1, len(points)):
        prev = points[i - 1]["equity"]
        curr = points[i]["equity"]
        if prev > 0:
            returns.append((curr - prev) / prev)
    return returns


def _filter_window(points: list[dict], days: int) -> list[dict]:
    if not points:
        return []
    cutoff = datetime.now() - timedelta(days=days)
    filtered = [p for p in points if _parse_ts(p.get("timestamp", "")) >= cutoff]
    return filtered or points[-min(days + 1, len(points)) :]


def _parse_ts(s: str) -> datetime:
    try:
        return datetime.fromisoformat(s)
    except (ValueError, TypeError):
        return datetime(1970, 1, 1)


def _sharpe(returns: list[float], risk_free: float = 0.0) -> float:
    if len(returns) < 2:
        return 0.0
    mean_r = sum(returns) / len(returns)
    var = sum((r - mean_r) ** 2 for r in returns) / len(returns)
    std = math.sqrt(var)
    if std == 0:
        return 0.0
    return ((mean_r - risk_free / TRADING_DAYS_PER_YEAR) / std) * math.sqrt(TRADING_DAYS_PER_YEAR)


def _sortino(returns: list[float], risk_free: float = 0.0) -> float:
    if len(returns) < 2:
        return 0.0
    mean_r = sum(returns) / len(returns)
    downside = [r for r in returns if r < 0]
    if not downside:
        return 0.0
    down_var = sum(r**2 for r in downside) / len(returns)
    down_std = math.sqrt(down_var)
    if down_std == 0:
        return 0.0
    return ((mean_r - risk_free / TRADING_DAYS_PER_YEAR) / down_std) * math.sqrt(TRADING_DAYS_PER_YEAR)


def _max_drawdown(points: list[dict]) -> float:
    if not points:
        return 0.0
    values = [p["equity"] for p in points]
    peak = values[0]
    max_dd = 0.0
    for v in values:
        peak = max(peak, v)
        dd = (peak - v) / peak if peak else 0.0
        max_dd = max(max_dd, dd)
    return max_dd


def _calmar(points: list[dict], returns: list[float]) -> float:
    mdd = _max_drawdown(points)
    if mdd == 0 or not returns:
        return 0.0
    mean_r = sum(returns) / len(returns)
    annualized = mean_r * TRADING_DAYS_PER_YEAR
    return annualized / mdd


def rolling_metrics(points: list[dict], window_days: int) -> dict:
    window = _filter_window(points, window_days)
    returns = _returns_from_equity(window)
    if not returns:
        return {
            "window_days": window_days,
            "samples": 0,
            "sharpe": 0.0,
            "sortino": 0.0,
            "calmar": 0.0,
            "max_drawdown_pct": 0.0,
            "total_return_pct": 0.0,
        }

    initial = window[0]["equity"]
    final = window[-1]["equity"]
    total_return = (final - initial) / initial if initial else 0.0

    return {
        "window_days": window_days,
        "samples": len(returns),
        "sharpe": round(_sharpe(returns), 3),
        "sortino": round(_sortino(returns), 3),
        "calmar": round(_calmar(window, returns), 3),
        "max_drawdown_pct": round(_max_drawdown(window) * 100, 2),
        "total_return_pct": round(total_return * 100, 2),
    }


def performance_snapshot() -> dict:
    try:
        points = paper_broker.get_equity_history(limit=10_000)
    except Exception:
        points = []
    return {
        "d7": rolling_metrics(points, 7),
        "d30": rolling_metrics(points, 30),
        "d90": rolling_metrics(points, 90),
        "total_points": len(points),
    }
