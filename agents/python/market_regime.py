from __future__ import annotations

import time
from dataclasses import dataclass

import structlog

log = structlog.get_logger(__name__)

_CACHE: dict[str, tuple[float, object]] = {}
_TTL_SEC = 1800


@dataclass
class MarketRegime:
    label: str
    breadth_pct: float
    above_50ma: int
    total: int
    vix: float
    macro_regime: str
    buy_mult: float
    sell_mult: float
    notes: list[str]


def _breadth(symbols: list[str]) -> tuple[float, int, int]:
    from agents.python.data_collector import fetch_candles
    from agents.python.indicators import _to_df, calc_sma

    above = 0
    total = 0
    for sym in symbols:
        try:
            candles = fetch_candles(sym, period="6mo")
        except Exception:
            continue
        if len(candles) < 60:
            continue
        df = _to_df(candles)
        closes = df["close"]
        sma50 = calc_sma(closes, 50)
        last_sma = float(sma50.iloc[-1]) if not sma50.empty else 0.0
        last_price = float(closes.iloc[-1])
        if last_sma <= 0:
            continue
        total += 1
        if last_price > last_sma:
            above += 1

    pct = above / total if total else 0.5
    return round(pct * 100, 1), above, total


def _combine(breadth_pct: float, vix: float, macro_regime: str) -> tuple[str, float, float, list[str]]:
    notes: list[str] = []
    buy_mult = 1.0
    sell_mult = 1.0

    if breadth_pct >= 70 and vix and vix < 18:
        notes.append(f"breadth {breadth_pct}% + VIX {vix:.1f} → risk-on")
        buy_mult = 1.08
        sell_mult = 0.9
        label = "risk_on"
    elif breadth_pct <= 30 and vix and vix > 25:
        notes.append(f"breadth {breadth_pct}% + VIX {vix:.1f} → risk-off")
        buy_mult = 0.85
        sell_mult = 1.1
        label = "risk_off"
    elif breadth_pct >= 60 or macro_regime == "risk_on":
        notes.append(f"breadth {breadth_pct}%, macro {macro_regime} → mild risk-on")
        buy_mult = 1.04
        sell_mult = 0.95
        label = "mild_risk_on"
    elif breadth_pct <= 40 or macro_regime == "risk_off":
        notes.append(f"breadth {breadth_pct}%, macro {macro_regime} → mild risk-off")
        buy_mult = 0.93
        sell_mult = 1.05
        label = "mild_risk_off"
    else:
        notes.append(f"breadth {breadth_pct}%, macro {macro_regime} → neutral")
        label = "neutral"

    return label, round(buy_mult, 3), round(sell_mult, 3), notes


def detect(symbols: list[str]) -> MarketRegime:
    key = "::".join(sorted(symbols))
    now = time.time()
    cached = _CACHE.get(key)
    if cached and now - cached[0] < _TTL_SEC:
        return cached[1]

    breadth_pct, above, total = _breadth(symbols)

    vix = 0.0
    macro_label = "neutral"
    try:
        from agents.python.macro import fetch_macro

        snap = fetch_macro()
        vix = snap.vix
        macro_label = snap.risk_regime or "neutral"
    except Exception as e:
        log.warning("macro_fetch_failed", error=str(e))

    label, buy_mult, sell_mult, notes = _combine(breadth_pct, vix, macro_label)
    regime = MarketRegime(
        label=label,
        breadth_pct=breadth_pct,
        above_50ma=above,
        total=total,
        vix=vix,
        macro_regime=macro_label,
        buy_mult=buy_mult,
        sell_mult=sell_mult,
        notes=notes,
    )
    _CACHE[key] = (now, regime)
    return regime


def apply_regime_to_votes(votes: list, symbols: list[str]) -> list:
    if not votes or not symbols:
        return votes
    try:
        regime = detect(symbols)
    except Exception as e:
        log.warning("regime_detect_failed", error=str(e))
        return votes

    for v in votes:
        mult = regime.buy_mult if v.action == "buy" else regime.sell_mult
        v.confidence = min(0.95, v.confidence * mult)
    return votes


def reset_cache() -> None:
    _CACHE.clear()
