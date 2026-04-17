from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import structlog

from agents.python import paper_broker
from config.settings import settings
from core import notifier

log = structlog.get_logger(__name__)


def _state_path() -> Path:
    p = settings.data_dir
    p.mkdir(parents=True, exist_ok=True)
    return p / "daily_digest_state.json"


def _load_state() -> dict:
    path = _state_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_state(state: dict) -> None:
    _state_path().write_text(json.dumps(state, indent=2), encoding="utf-8")


def _today_trades() -> list[dict]:
    midnight = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    try:
        with sqlite3.connect(paper_broker._db_path()) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT symbol, pnl, pnl_pct, close_reason, closed_at FROM trades "
                "WHERE closed_at IS NOT NULL AND closed_at >= ? ORDER BY closed_at",
                (midnight,),
            ).fetchall()
    except sqlite3.OperationalError:
        return []
    return [dict(r) for r in rows]


def _equity_24h_ago() -> float | None:
    cutoff = (datetime.now() - timedelta(hours=24)).isoformat()
    try:
        with sqlite3.connect(paper_broker._db_path()) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT equity FROM equity_curve WHERE timestamp <= ? ORDER BY timestamp DESC LIMIT 1",
                (cutoff,),
            ).fetchone()
    except sqlite3.OperationalError:
        return None
    return float(row["equity"]) if row else None


def build_summary() -> str:
    trades = _today_trades()
    wins = [t for t in trades if (t["pnl"] or 0) > 0]
    losses = [t for t in trades if (t["pnl"] or 0) <= 0 and t["pnl"] is not None]
    total_pnl = sum(t["pnl"] or 0.0 for t in trades)
    win_rate = len(wins) / len(trades) * 100 if trades else 0.0

    try:
        acc = paper_broker.get_account()
        equity_now = float(acc.get("equity", 0.0))
    except Exception:
        equity_now = 0.0
    equity_prev = _equity_24h_ago()
    change_24h = equity_now - equity_prev if equity_prev else 0.0
    change_pct = (change_24h / equity_prev * 100) if equity_prev else 0.0

    regime_line = ""
    try:
        from agents.python.market_regime import detect

        regime = detect(settings.symbols)
        regime_line = f"Режим: `{regime.label}` • breadth {regime.breadth_pct}% • VIX {regime.vix:.1f}"
    except Exception:
        regime_line = "Режим: `недоступний`"

    top_voters = ""
    try:
        from agents.python.voter_stats import get_all_stats, get_weight

        stats = sorted(get_all_stats(), key=lambda s: -s.win_rate)[:3]
        if stats:
            rows = [
                f"  • `{s.voter}`: WR {s.win_rate * 100:.0f}% (n={s.total}) × weight {get_weight(s.voter):.2f}"
                for s in stats
            ]
            top_voters = "\n".join(rows)
    except Exception:
        top_voters = ""

    breaker_line = ""
    try:
        from agents.python.circuit_breaker import check_drawdown, check_loss_streak

        dd = check_drawdown()
        streak = check_loss_streak(settings.max_consecutive_losses, settings.loss_cooldown_hours)
        if dd["tripped"]:
            breaker_line = f"\n⛔ *Drawdown breaker:* {dd['current_dd_pct']}%"
        elif streak["tripped"]:
            breaker_line = f"\n⛔ *Loss-streak cooldown:* {streak['streak']} поспіль"
    except Exception:
        pass

    emoji = "📈" if total_pnl > 0 else "📉" if total_pnl < 0 else "➖"
    header = f"{emoji} *Daily digest {datetime.now():%Y-%m-%d}*"

    lines = [
        header,
        "",
        f"Equity: `${equity_now:,.2f}`",
        f"24h change: `{change_24h:+.2f}$` ({change_pct:+.2f}%)",
        "",
        f"Угод закрито: `{len(trades)}` (win {len(wins)}, loss {len(losses)})",
        f"Win rate: `{win_rate:.1f}%`",
        f"Realised PnL сьогодні: `${total_pnl:+.2f}`",
        "",
        regime_line,
    ]
    if top_voters:
        lines.append("")
        lines.append("*Топ voters:*")
        lines.append(top_voters)
    if breaker_line:
        lines.append(breaker_line)

    return "\n".join(lines)


async def send_if_due(min_hours: int = 20) -> bool:
    state = _load_state()
    last = state.get("last_sent_at")
    if last:
        try:
            last_dt = datetime.fromisoformat(last)
            age_hours = (datetime.now() - last_dt).total_seconds() / 3600
            if age_hours < min_hours:
                return False
        except ValueError:
            pass

    summary = build_summary()
    ok = await notifier.send_telegram(summary)
    if ok:
        state["last_sent_at"] = datetime.now().isoformat()
        _save_state(state)
    return ok


async def force_send() -> bool:
    return await notifier.send_telegram(build_summary())
