from __future__ import annotations

from datetime import datetime, timedelta

from agents.python import paper_broker


def check_drawdown(window_days: int = 7, threshold_pct: float = 10.0) -> dict:
    equity_history = paper_broker.get_equity_history(limit=10000)
    if len(equity_history) < 2:
        return {"tripped": False, "reason": "insufficient history", "current_dd_pct": 0.0}

    cutoff = (datetime.now() - timedelta(days=window_days)).isoformat()
    recent = [p for p in equity_history if p["timestamp"] >= cutoff]
    if len(recent) < 2:
        recent = equity_history[-max(2, min(len(equity_history), 20)) :]

    peak = max(p["equity"] for p in recent)
    current = recent[-1]["equity"]
    dd_pct = (peak - current) / peak * 100 if peak else 0

    return {
        "tripped": dd_pct >= threshold_pct,
        "current_dd_pct": round(dd_pct, 2),
        "threshold_pct": threshold_pct,
        "window_days": window_days,
        "peak_equity": round(peak, 2),
        "current_equity": round(current, 2),
    }


def is_trading_hours() -> dict:
    now = datetime.now()
    weekday = now.weekday()

    is_weekend = weekday >= 5
    hour = now.hour

    us_market_open = 16 <= hour < 23
    crypto_always_open = True

    return {
        "is_weekend": is_weekend,
        "us_market_open": not is_weekend and us_market_open,
        "crypto_open": crypto_always_open,
        "hour_local": hour,
        "weekday": weekday,
        "should_trade_stocks": not is_weekend and us_market_open,
    }


def should_block_trading(max_drawdown_pct: float = 10.0) -> tuple[bool, str]:
    dd = check_drawdown(threshold_pct=max_drawdown_pct)
    if dd["tripped"]:
        return True, f"circuit_breaker: drawdown {dd['current_dd_pct']}% exceeds {max_drawdown_pct}%"

    return False, "ok"
