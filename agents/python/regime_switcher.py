from __future__ import annotations

from datetime import datetime
from pathlib import Path

import orjson

from agents.python.data_collector import fetch_candles
from agents.python.regime_detector import detect_portfolio_regime
from config.settings import settings


def _state_path() -> Path:
    return settings.data_dir / "active_strategy.json"


def load_active_strategy() -> dict:
    path = _state_path()
    if not path.exists():
        return {"strategy": "bb_mean_reversion", "regime": "unknown", "last_switch": ""}
    try:
        return orjson.loads(path.read_bytes())
    except Exception:
        return {"strategy": "bb_mean_reversion", "regime": "unknown", "last_switch": ""}


def save_active_strategy(strategy: str, regime: str, confidence: float) -> None:
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "strategy": strategy,
        "regime": regime,
        "confidence": confidence,
        "last_switch": datetime.now().isoformat(),
    }
    path.write_bytes(orjson.dumps(payload, option=orjson.OPT_INDENT_2))


def auto_switch_strategy(min_confidence: float = 0.5) -> dict:
    data = {}
    for sym in settings.symbols[:5]:
        candles = fetch_candles(sym, period="3mo")
        if candles:
            data[sym] = candles

    if not data:
        return {"switched": False, "reason": "no market data"}

    regime_info = detect_portfolio_regime(data)
    regime = regime_info["regime"]
    confidence = regime_info["confidence"]
    recommended = regime_info["strategy"]

    current = load_active_strategy()
    current_strategy = current.get("strategy", "bb_mean_reversion")

    if confidence < min_confidence:
        return {
            "switched": False,
            "reason": f"regime confidence {confidence:.2f} below threshold {min_confidence}",
            "current_strategy": current_strategy,
            "detected_regime": regime,
        }

    if recommended == current_strategy:
        return {
            "switched": False,
            "reason": "already using optimal strategy",
            "current_strategy": current_strategy,
            "detected_regime": regime,
        }

    save_active_strategy(recommended, regime, confidence)

    return {
        "switched": True,
        "from_strategy": current_strategy,
        "to_strategy": recommended,
        "regime": regime,
        "confidence": confidence,
        "reason": f"regime changed to {regime} — switching to {recommended}",
    }


def get_current_strategy_for_backtest() -> str:
    return load_active_strategy().get("strategy", "bb_mean_reversion")


def override_strategy(strategy_name: str) -> dict:
    valid = {"bb_mean_reversion", "momentum", "momentum_breakout"}
    if strategy_name not in valid:
        return {"success": False, "error": f"unknown strategy: {strategy_name}", "valid": list(valid)}

    save_active_strategy(strategy_name, "manual_override", 1.0)
    return {"success": True, "strategy": strategy_name}
