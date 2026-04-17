from __future__ import annotations

from datetime import datetime

from agents.python import paper_broker


def snapshot(prices: dict[str, float] | None = None) -> dict:
    account = paper_broker.get_account()
    positions = paper_broker.list_positions(prices or {})

    return {
        "timestamp": datetime.now().isoformat(),
        "account": account,
        "positions": positions,
        "open_count": len(positions),
        "total_unrealized_pl": sum(p.get("unrealized_pl", 0) for p in positions),
    }


def save_snapshot(snap: dict):
    pass


def log_trade(trade_result: dict):
    pass


def summary() -> dict:
    stats = paper_broker.get_trade_stats()
    return {
        "total_trades": stats["total_trades"],
        "win_rate": stats["win_rate"],
        "total_pl": stats["total_pnl"],
        "wins": stats["wins"],
        "losses": stats["losses"],
        "avg_win": stats["avg_win"],
        "avg_loss": stats["avg_loss"],
    }


def equity_history(limit: int = 100) -> list[dict]:
    return paper_broker.get_equity_history(limit)


def reset():
    paper_broker.reset_account()
