from __future__ import annotations

import math

from agents.python.indicators import _to_df, calc_adx, calc_atr


def detect_regime(candles: list[dict]) -> dict:
    df = _to_df(candles)
    if df.empty or len(df) < 30:
        return {"regime": "unknown", "confidence": 0.0, "metrics": {}}

    closes = df["close"]
    adx = calc_adx(df)
    atr = calc_atr(df)

    change_20d = (closes.iloc[-1] - closes.iloc[-20]) / closes.iloc[-20] * 100 if len(closes) >= 20 else 0
    change_50d = (closes.iloc[-1] - closes.iloc[-50]) / closes.iloc[-50] * 100 if len(closes) >= 50 else 0

    returns = closes.pct_change().dropna()
    recent_returns = returns.tail(20)
    vol_annualized = recent_returns.std() * math.sqrt(252) * 100 if len(recent_returns) > 1 else 0

    atr_pct = atr / closes.iloc[-1] * 100 if closes.iloc[-1] else 0

    if adx > 25 and change_20d > 5:
        regime = "bull_trend"
        confidence = min(0.95, 0.6 + (adx - 25) / 100)
    elif adx > 25 and change_20d < -5:
        regime = "bear_trend"
        confidence = min(0.95, 0.6 + (adx - 25) / 100)
    elif adx < 20 and vol_annualized < 25:
        regime = "low_vol_range"
        confidence = 0.7
    elif adx < 25 and abs(change_20d) < 3:
        regime = "choppy"
        confidence = 0.6
    elif vol_annualized > 45:
        regime = "high_vol"
        confidence = 0.75
    else:
        regime = "neutral"
        confidence = 0.5

    return {
        "regime": regime,
        "confidence": round(confidence, 3),
        "metrics": {
            "adx": round(adx, 2),
            "change_20d_pct": round(change_20d, 2),
            "change_50d_pct": round(change_50d, 2),
            "annualized_vol_pct": round(vol_annualized, 2),
            "atr_pct": round(atr_pct, 2),
        },
    }


def pick_strategy(regime: str) -> str:
    mapping = {
        "bull_trend": "momentum",
        "bear_trend": "momentum",
        "low_vol_range": "bb_mean_reversion",
        "choppy": "bb_mean_reversion",
        "high_vol": "momentum_breakout",
        "neutral": "bb_mean_reversion",
        "unknown": "bb_mean_reversion",
    }
    return mapping.get(regime, "bb_mean_reversion")


def detect_portfolio_regime(market_data_by_symbol: dict[str, list[dict]]) -> dict:
    regimes: list[str] = []
    confidences: list[float] = []

    for candles in market_data_by_symbol.values():
        r = detect_regime(candles)
        regimes.append(r["regime"])
        confidences.append(r["confidence"])

    if not regimes:
        return {"regime": "unknown", "confidence": 0.0, "strategy": "bb_mean_reversion"}

    counts: dict[str, int] = {}
    for r in regimes:
        counts[r] = counts.get(r, 0) + 1

    dominant = max(counts.items(), key=lambda x: x[1])[0]
    dominance_pct = counts[dominant] / len(regimes)
    avg_conf = sum(confidences) / len(confidences) if confidences else 0

    return {
        "regime": dominant,
        "confidence": round(avg_conf * dominance_pct, 3),
        "dominance_pct": round(dominance_pct, 2),
        "strategy": pick_strategy(dominant),
        "breakdown": counts,
    }
