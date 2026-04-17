from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import orjson

from agents.python import paper_broker
from config.settings import settings


def _tuner_state_path() -> Path:
    return settings.data_dir / "auto_tuner.json"


def _load_state() -> dict:
    path = _tuner_state_path()
    if not path.exists():
        return {"last_run": "", "adjustments": [], "current_params": {}}
    try:
        return orjson.loads(path.read_bytes())
    except Exception:
        return {"last_run": "", "adjustments": [], "current_params": {}}


def _save_state(state: dict) -> None:
    path = _tuner_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(orjson.dumps(state, option=orjson.OPT_INDENT_2))


def _load_recent_trades(days: int = 7) -> list[dict]:
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    with sqlite3.connect(paper_broker._db_path()) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM trades WHERE closed_at IS NOT NULL AND closed_at >= ? ORDER BY id ASC",
            (cutoff,),
        ).fetchall()
    return [dict(r) for r in rows]


def _analyze_trades(trades: list[dict]) -> dict:
    if not trades:
        return {"count": 0, "suggestions": []}

    wins = [t for t in trades if (t.get("pnl") or 0) > 0]
    losses = [t for t in trades if (t.get("pnl") or 0) < 0]

    win_rate = len(wins) / len(trades) if trades else 0
    avg_win = sum(t["pnl"] for t in wins) / len(wins) if wins else 0
    avg_loss = sum(t["pnl"] for t in losses) / len(losses) if losses else 0

    suggestions: list[dict] = []

    if win_rate < 0.35 and len(trades) >= 5:
        suggestions.append(
            {
                "param": "confidence_threshold",
                "action": "increase",
                "delta": 0.05,
                "reason": f"Low win rate {win_rate:.0%}, raise entry confidence bar",
            }
        )

    if wins and losses and abs(avg_loss) > avg_win:
        suggestions.append(
            {
                "param": "take_profit_multiplier",
                "action": "increase",
                "delta": 0.5,
                "reason": f"Losses (${abs(avg_loss):.0f}) exceed wins (${avg_win:.0f}), widen TP",
            }
        )

    stop_loss_exits = sum(1 for t in trades if t.get("close_reason") == "stop_loss")
    sl_rate = stop_loss_exits / len(trades) if trades else 0
    if sl_rate > 0.5:
        suggestions.append(
            {
                "param": "stop_loss_multiplier",
                "action": "increase",
                "delta": 0.3,
                "reason": f"{sl_rate:.0%} trades hit stop — widen SL",
            }
        )

    reversal_exits = sum(1 for t in trades if t.get("close_reason") == "signal_reversal")
    if reversal_exits / max(len(trades), 1) > 0.3:
        suggestions.append(
            {
                "param": "reversal_confidence",
                "action": "increase",
                "delta": 0.05,
                "reason": "Too many premature reversal exits — raise reversal threshold",
            }
        )

    return {
        "count": len(trades),
        "win_rate": round(win_rate, 3),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "stop_loss_rate": round(sl_rate, 3),
        "suggestions": suggestions,
    }


def run_tuning_cycle(force: bool = False) -> dict:
    state = _load_state()

    if not force and state.get("last_run"):
        try:
            last = datetime.fromisoformat(state["last_run"])
            if (datetime.now() - last).days < 7:
                return {
                    "status": "skipped",
                    "reason": "last tuning less than 7 days ago",
                    "last_run": state["last_run"],
                }
        except Exception:
            pass

    trades = _load_recent_trades(days=7)
    analysis = _analyze_trades(trades)

    if not analysis["suggestions"]:
        result = {"status": "no_changes_needed", "analysis": analysis}
    else:
        adjustment = {
            "timestamp": datetime.now().isoformat(),
            "analysis": analysis,
            "applied": analysis["suggestions"],
        }
        state.setdefault("adjustments", []).append(adjustment)
        state["adjustments"] = state["adjustments"][-20:]
        result = {"status": "applied", "adjustment": adjustment}

    state["last_run"] = datetime.now().isoformat()
    _save_state(state)

    return result


def get_tuning_history(limit: int = 10) -> list[dict]:
    state = _load_state()
    return state.get("adjustments", [])[-limit:]


def reset_tuner() -> None:
    path = _tuner_state_path()
    if path.exists():
        path.unlink()
