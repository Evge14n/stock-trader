from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from config.settings import settings

INITIAL_CASH = 100_000.0


def _db_path() -> Path:
    return settings.data_dir / "paper_broker.db"


def _init_db(conn: sqlite3.Connection):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS account (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            cash REAL NOT NULL,
            initial_deposit REAL NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS positions (
            symbol TEXT PRIMARY KEY,
            qty INTEGER NOT NULL,
            avg_entry REAL NOT NULL,
            stop_loss REAL,
            take_profit REAL,
            opened_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            qty INTEGER NOT NULL,
            price REAL NOT NULL,
            stop_loss REAL,
            take_profit REAL,
            confidence REAL,
            reasoning TEXT,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            qty INTEGER NOT NULL,
            entry_price REAL NOT NULL,
            exit_price REAL,
            pnl REAL,
            pnl_pct REAL,
            opened_at TEXT NOT NULL,
            closed_at TEXT,
            close_reason TEXT
        );
        CREATE TABLE IF NOT EXISTS equity_curve (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            cash REAL NOT NULL,
            positions_value REAL NOT NULL,
            equity REAL NOT NULL,
            unrealized_pl REAL NOT NULL
        );
    """)

    row = conn.execute("SELECT id FROM account WHERE id = 1").fetchone()
    if not row:
        conn.execute(
            "INSERT INTO account (id, cash, initial_deposit, created_at) VALUES (1, ?, ?, ?)",
            (INITIAL_CASH, INITIAL_CASH, datetime.now().isoformat()),
        )
    conn.commit()


@contextmanager
def _conn():
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    _init_db(conn)
    try:
        yield conn
    finally:
        conn.close()


def get_account() -> dict:
    with _conn() as c:
        row = c.execute("SELECT * FROM account WHERE id = 1").fetchone()
        positions = list_positions(prices={})

        positions_value = 0.0
        for p in positions:
            positions_value += p["qty"] * p["avg_entry"]

        return {
            "cash": row["cash"],
            "initial_deposit": row["initial_deposit"],
            "positions_value": positions_value,
            "equity": row["cash"] + positions_value,
            "buying_power": row["cash"],
            "created_at": row["created_at"],
        }


def list_positions(prices: dict[str, float] | None = None) -> list[dict]:
    prices = prices or {}
    with _conn() as c:
        rows = c.execute("SELECT * FROM positions").fetchall()

    result = []
    for r in rows:
        current = prices.get(r["symbol"], r["avg_entry"])
        unrealized_pl = (current - r["avg_entry"]) * r["qty"]
        unrealized_plpc = (current - r["avg_entry"]) / r["avg_entry"] if r["avg_entry"] else 0.0
        result.append(
            {
                "symbol": r["symbol"],
                "qty": r["qty"],
                "side": "long" if r["qty"] > 0 else "short",
                "avg_entry": r["avg_entry"],
                "current_price": current,
                "unrealized_pl": round(unrealized_pl, 2),
                "unrealized_plpc": round(unrealized_plpc, 4),
                "stop_loss": r["stop_loss"],
                "take_profit": r["take_profit"],
                "opened_at": r["opened_at"],
            }
        )
    return result


def submit_order(
    symbol: str,
    qty: int,
    side: str,
    price: float,
    stop_loss: float | None = None,
    take_profit: float | None = None,
    confidence: float = 0.0,
    reasoning: str = "",
) -> dict:
    now = datetime.now().isoformat()

    with _conn() as c:
        cost = qty * price
        account = c.execute("SELECT cash FROM account WHERE id = 1").fetchone()
        existing = c.execute("SELECT * FROM positions WHERE symbol = ?", (symbol,)).fetchone()

        if side == "buy":
            if cost > account["cash"]:
                status = "rejected_insufficient_cash"
            elif existing:
                status = "rejected_already_holding"
            else:
                c.execute(
                    "INSERT INTO positions (symbol, qty, avg_entry, stop_loss, take_profit, opened_at) VALUES (?,?,?,?,?,?)",
                    (symbol, qty, price, stop_loss, take_profit, now),
                )
                c.execute("UPDATE account SET cash = cash - ? WHERE id = 1", (cost,))
                status = "filled"

        elif side == "sell":
            if not existing:
                status = "rejected_no_position"
            else:
                proceeds = existing["qty"] * price
                pnl = (price - existing["avg_entry"]) * existing["qty"]
                pnl_pct = (price - existing["avg_entry"]) / existing["avg_entry"] if existing["avg_entry"] else 0.0

                c.execute("UPDATE account SET cash = cash + ? WHERE id = 1", (proceeds,))
                c.execute("DELETE FROM positions WHERE symbol = ?", (symbol,))
                c.execute(
                    "INSERT INTO trades (symbol, side, qty, entry_price, exit_price, pnl, pnl_pct, opened_at, closed_at, close_reason) VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (
                        symbol,
                        "long",
                        existing["qty"],
                        existing["avg_entry"],
                        price,
                        round(pnl, 2),
                        round(pnl_pct, 4),
                        existing["opened_at"],
                        now,
                        "signal_exit",
                    ),
                )
                status = "filled"
        else:
            status = "rejected_invalid_side"

        c.execute(
            "INSERT INTO orders (symbol, side, qty, price, stop_loss, take_profit, confidence, reasoning, status, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (symbol, side, qty, price, stop_loss, take_profit, confidence, reasoning[:500], status, now),
        )
        c.commit()
        order_id = c.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]

    return {
        "id": order_id,
        "symbol": symbol,
        "side": side,
        "qty": qty,
        "price": price,
        "status": status,
        "submitted_at": now,
    }


def update_trailing_stops(prices: dict[str, float], trail_pct: float = 0.03) -> int:
    updated = 0
    with _conn() as c:
        rows = c.execute("SELECT * FROM positions").fetchall()
        for pos in rows:
            price = prices.get(pos["symbol"])
            if not price or pos["qty"] <= 0:
                continue
            new_stop = round(price * (1 - trail_pct), 2)
            if pos["stop_loss"] and new_stop > pos["stop_loss"] and price > pos["avg_entry"]:
                c.execute("UPDATE positions SET stop_loss = ? WHERE symbol = ?", (new_stop, pos["symbol"]))
                updated += 1
        c.commit()
    return updated


def check_stop_targets(prices: dict[str, float]) -> list[dict]:
    closed = []
    with _conn() as c:
        rows = c.execute("SELECT * FROM positions").fetchall()

    for pos in rows:
        price = prices.get(pos["symbol"])
        if not price:
            continue

        reason = None
        if pos["qty"] > 0:
            if pos["stop_loss"] and price <= pos["stop_loss"]:
                reason = "stop_loss"
            elif pos["take_profit"] and price >= pos["take_profit"]:
                reason = "take_profit"

        if reason:
            result = submit_order(pos["symbol"], pos["qty"], "sell", price)
            result["close_reason"] = reason
            closed.append(result)

    return closed


def record_equity(prices: dict[str, float]):
    positions = list_positions(prices)
    positions_value = sum(p["qty"] * p["current_price"] for p in positions)
    unrealized = sum(p["unrealized_pl"] for p in positions)

    with _conn() as c:
        cash = c.execute("SELECT cash FROM account WHERE id = 1").fetchone()["cash"]
        c.execute(
            "INSERT INTO equity_curve (timestamp, cash, positions_value, equity, unrealized_pl) VALUES (?,?,?,?,?)",
            (datetime.now().isoformat(), cash, positions_value, cash + positions_value, unrealized),
        )
        c.commit()


def get_trade_stats() -> dict:
    with _conn() as c:
        rows = c.execute("SELECT * FROM trades WHERE closed_at IS NOT NULL").fetchall()

    if not rows:
        return {
            "total_trades": 0,
            "wins": 0,
            "losses": 0,
            "win_rate": 0.0,
            "total_pnl": 0.0,
            "avg_win": 0.0,
            "avg_loss": 0.0,
        }

    wins = [r for r in rows if r["pnl"] and r["pnl"] > 0]
    losses = [r for r in rows if r["pnl"] and r["pnl"] < 0]
    total_pnl = sum(r["pnl"] or 0 for r in rows)

    return {
        "total_trades": len(rows),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(len(wins) / len(rows), 3) if rows else 0.0,
        "total_pnl": round(total_pnl, 2),
        "avg_win": round(sum(r["pnl"] for r in wins) / len(wins), 2) if wins else 0.0,
        "avg_loss": round(sum(r["pnl"] for r in losses) / len(losses), 2) if losses else 0.0,
    }


def get_equity_history(limit: int = 100) -> list[dict]:
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM equity_curve ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in reversed(rows)]


def reset_account():
    path = _db_path()
    if path.exists():
        path.unlink()
