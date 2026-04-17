from __future__ import annotations

import time

import structlog

from agents.python.correlation import compute_correlation_matrix

log = structlog.get_logger(__name__)

_CACHE: dict[str, tuple[float, dict]] = {}
_TTL_SEC = 3600


def _cache_key(symbols: list[str], period: str) -> str:
    return f"{period}::{','.join(sorted(symbols))}"


def _cached_matrix(symbols: list[str], period: str = "3mo") -> dict:
    key = _cache_key(symbols, period)
    now = time.time()
    cached = _CACHE.get(key)
    if cached and now - cached[0] < _TTL_SEC:
        return cached[1]

    try:
        matrix = compute_correlation_matrix(symbols, period=period)
    except Exception as e:
        log.warning("correlation_fetch_failed", error=str(e))
        return {"matrix": {}, "symbols": symbols}

    _CACHE[key] = (now, matrix)
    return matrix


def reset_cache() -> None:
    _CACHE.clear()


def max_correlation(
    symbol: str,
    existing_positions: list[str],
    period: str = "3mo",
) -> float:
    if not existing_positions or symbol in existing_positions:
        return 0.0

    data = _cached_matrix(list({symbol, *existing_positions}), period=period)
    matrix = data.get("matrix", {})
    row = matrix.get(symbol, {})
    if not row:
        return 0.0

    highest = 0.0
    for held in existing_positions:
        if held == symbol:
            continue
        val = row.get(held)
        if val is None:
            continue
        highest = max(highest, abs(float(val)))
    return highest


def size_factor(
    symbol: str,
    existing_positions: list[str],
    threshold: float = 0.7,
    max_cut: float = 0.5,
    period: str = "3mo",
) -> tuple[float, float]:
    max_corr = max_correlation(symbol, existing_positions, period=period)
    if max_corr < threshold:
        return 1.0, max_corr

    overage = max_corr - threshold
    factor = max(max_cut, 1.0 - overage * 2.0)
    return round(factor, 3), round(max_corr, 3)
