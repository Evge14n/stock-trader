from __future__ import annotations

import time
from dataclasses import dataclass

import structlog

from agents.python.data_collector import fetch_candles

log = structlog.get_logger(__name__)

_CACHE: dict[str, tuple[float, dict]] = {}
_TTL_SEC = 3600


@dataclass
class RSRank:
    symbol: str
    return_pct: float
    rank: int
    percentile: float


def _compute_return(candles: list[dict], lookback: int) -> float | None:
    if not candles or len(candles) <= lookback:
        return None
    start_close = candles[-lookback - 1]["close"]
    end_close = candles[-1]["close"]
    if start_close <= 0:
        return None
    return (end_close - start_close) / start_close


def _rank_watchlist(symbols: list[str], lookback_days: int, period: str) -> list[RSRank]:
    returns: dict[str, float] = {}
    for sym in symbols:
        try:
            candles = fetch_candles(sym, period=period)
        except Exception as e:
            log.warning("rs_fetch_failed", symbol=sym, error=str(e))
            continue
        r = _compute_return(candles, lookback_days)
        if r is not None:
            returns[sym] = r

    if not returns:
        return []

    sorted_items = sorted(returns.items(), key=lambda x: x[1], reverse=True)
    total = len(sorted_items)
    out = []
    for rank, (sym, r) in enumerate(sorted_items, start=1):
        percentile = 1.0 - (rank - 1) / total if total > 1 else 1.0
        out.append(RSRank(symbol=sym, return_pct=round(r * 100, 2), rank=rank, percentile=round(percentile, 3)))
    return out


def ranked(symbols: list[str], lookback_days: int = 20, period: str = "3mo") -> list[RSRank]:
    key = f"{period}::{lookback_days}::{','.join(sorted(symbols))}"
    now = time.time()
    cached = _CACHE.get(key)
    if cached and now - cached[0] < _TTL_SEC:
        return cached[1]
    result = _rank_watchlist(symbols, lookback_days, period)
    _CACHE[key] = (now, result)
    return result


def rank_for(symbol: str, universe: list[str], lookback_days: int = 20, period: str = "3mo") -> RSRank | None:
    if symbol not in universe:
        universe = [*universe, symbol]
    ranks = ranked(universe, lookback_days=lookback_days, period=period)
    return next((r for r in ranks if r.symbol == symbol), None)


def reset_cache() -> None:
    _CACHE.clear()
