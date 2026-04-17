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


def check_loss_streak(max_consecutive: int = 3, cooldown_hours: int = 24) -> dict:
    import sqlite3

    try:
        with sqlite3.connect(paper_broker._db_path()) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT pnl, closed_at FROM trades WHERE pnl IS NOT NULL AND closed_at IS NOT NULL "
                "ORDER BY closed_at DESC LIMIT ?",
                (max_consecutive + 10,),
            ).fetchall()
    except sqlite3.OperationalError:
        rows = []

    if not rows:
        return {"tripped": False, "streak": 0, "cooldown_active": False, "last_loss_at": None}

    streak = 0
    last_loss_ts = None
    for r in rows:
        if r["pnl"] < 0:
            streak += 1
            if last_loss_ts is None:
                last_loss_ts = r["closed_at"]
        else:
            break

    cooldown_active = False
    if streak >= max_consecutive and last_loss_ts:
        try:
            last_dt = datetime.fromisoformat(last_loss_ts)
            age_hours = (datetime.now() - last_dt).total_seconds() / 3600
            cooldown_active = age_hours < cooldown_hours
        except ValueError:
            cooldown_active = True

    return {
        "tripped": cooldown_active,
        "streak": streak,
        "max_consecutive": max_consecutive,
        "cooldown_active": cooldown_active,
        "cooldown_hours": cooldown_hours,
        "last_loss_at": last_loss_ts,
    }


def should_block_trading(max_drawdown_pct: float = 10.0) -> tuple[bool, str]:
    dd = check_drawdown(threshold_pct=max_drawdown_pct)
    if dd["tripped"]:
        return True, f"circuit_breaker: drawdown {dd['current_dd_pct']}% exceeds {max_drawdown_pct}%"

    from config.settings import settings

    streak = check_loss_streak(settings.max_consecutive_losses, settings.loss_cooldown_hours)
    if streak["tripped"]:
        return True, (
            f"circuit_breaker: {streak['streak']} consecutive losses, cooldown active for {streak['cooldown_hours']}h"
        )

    return False, "ok"
