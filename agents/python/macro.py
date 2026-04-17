from __future__ import annotations

from dataclasses import dataclass, field

import yfinance as yf


@dataclass
class MacroSnapshot:
    vix: float = 0.0
    vix_change_pct: float = 0.0
    dxy: float = 0.0
    dxy_change_pct: float = 0.0
    treasury_10y: float = 0.0
    treasury_10y_change_pct: float = 0.0
    gold: float = 0.0
    gold_change_pct: float = 0.0
    oil: float = 0.0
    oil_change_pct: float = 0.0
    btc: float = 0.0
    btc_change_pct: float = 0.0
    timestamp: str = ""
    risk_regime: str = ""
    risk_score: float = 0.0
    interpretation: list[str] = field(default_factory=list)


def _fetch_ticker_change(symbol: str) -> tuple[float, float]:
    try:
        hist = yf.Ticker(symbol).history(period="5d", interval="1d")
        if hist.empty or len(hist) < 2:
            return 0.0, 0.0
        last = float(hist["Close"].iloc[-1])
        prev = float(hist["Close"].iloc[-2])
        change = (last - prev) / prev * 100 if prev else 0.0
        return round(last, 4), round(change, 2)
    except Exception:
        return 0.0, 0.0


def _classify_risk_regime(snap: MacroSnapshot) -> tuple[str, float, list[str]]:
    score = 0.0
    notes: list[str] = []

    if snap.vix > 30:
        score -= 2
        notes.append(f"VIX {snap.vix:.1f} shows extreme fear")
    elif snap.vix > 20:
        score -= 1
        notes.append(f"VIX {snap.vix:.1f} elevated — caution")
    elif snap.vix < 15:
        score += 1
        notes.append(f"VIX {snap.vix:.1f} low — complacent market")

    if snap.vix_change_pct > 10:
        score -= 1
        notes.append(f"VIX spiking +{snap.vix_change_pct:.1f}% — risk-off")

    if snap.dxy_change_pct > 1:
        score -= 0.5
        notes.append("Dollar strengthening — pressure on stocks")
    elif snap.dxy_change_pct < -1:
        score += 0.5
        notes.append("Dollar weakening — supportive for equities")

    if snap.treasury_10y > 4.5:
        score -= 0.5
        notes.append(f"10Y yield {snap.treasury_10y:.2f}% high — growth stocks under pressure")
    elif snap.treasury_10y < 3.5:
        score += 0.5
        notes.append(f"10Y yield {snap.treasury_10y:.2f}% low — supportive")

    if snap.gold_change_pct > 2:
        notes.append(f"Gold +{snap.gold_change_pct:.1f}% — defensive flow")

    if snap.oil_change_pct > 3:
        notes.append(f"Oil +{snap.oil_change_pct:.1f}% — inflation risk")
    elif snap.oil_change_pct < -3:
        notes.append(f"Oil {snap.oil_change_pct:.1f}% — demand concern or supply glut")

    if score >= 1:
        regime = "risk_on"
    elif score <= -1.5:
        regime = "risk_off"
    else:
        regime = "neutral"

    return regime, round(score, 2), notes


def fetch_macro() -> MacroSnapshot:
    from datetime import datetime

    tickers = {
        "vix": "^VIX",
        "dxy": "DX-Y.NYB",
        "treasury_10y": "^TNX",
        "gold": "GLD",
        "oil": "USO",
        "btc": "BTC-USD",
    }

    snap = MacroSnapshot(timestamp=datetime.now().isoformat())

    for field_name, ticker in tickers.items():
        value, change = _fetch_ticker_change(ticker)
        setattr(snap, field_name, value)
        setattr(snap, f"{field_name}_change_pct", change)

    regime, score, notes = _classify_risk_regime(snap)
    snap.risk_regime = regime
    snap.risk_score = score
    snap.interpretation = notes

    return snap


def get_macro_summary() -> dict:
    snap = fetch_macro()
    return {
        "timestamp": snap.timestamp,
        "vix": snap.vix,
        "vix_change_pct": snap.vix_change_pct,
        "dxy": snap.dxy,
        "dxy_change_pct": snap.dxy_change_pct,
        "treasury_10y": snap.treasury_10y,
        "treasury_10y_change_pct": snap.treasury_10y_change_pct,
        "gold": snap.gold,
        "gold_change_pct": snap.gold_change_pct,
        "oil": snap.oil,
        "oil_change_pct": snap.oil_change_pct,
        "btc": snap.btc,
        "btc_change_pct": snap.btc_change_pct,
        "risk_regime": snap.risk_regime,
        "risk_score": snap.risk_score,
        "interpretation": snap.interpretation,
    }
