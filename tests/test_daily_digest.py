from __future__ import annotations

import asyncio
import sqlite3
from datetime import datetime, timedelta

from agents.python import daily_digest, paper_broker


def _today_ts(offset_minutes: int = 0) -> str:
    midnight = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    return (midnight + timedelta(hours=12, minutes=offset_minutes)).isoformat()


def _seed(trades: list[tuple[str, float, int]] = (), equity_points: list[float] = ()):
    with sqlite3.connect(paper_broker._db_path()) as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS trades (id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT NOT NULL, side TEXT NOT NULL, qty INTEGER NOT NULL, entry_price REAL NOT NULL, exit_price REAL, pnl REAL, pnl_pct REAL, opened_at TEXT NOT NULL, closed_at TEXT, close_reason TEXT);
            CREATE TABLE IF NOT EXISTS account (id INTEGER PRIMARY KEY CHECK (id = 1), cash REAL NOT NULL, initial_deposit REAL NOT NULL, created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS equity_curve (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT NOT NULL, cash REAL NOT NULL, positions_value REAL NOT NULL, equity REAL NOT NULL, unrealized_pl REAL NOT NULL);
        """)
        conn.execute(
            "INSERT OR REPLACE INTO account (id, cash, initial_deposit, created_at) VALUES (1, ?, 100000, ?)",
            (100_000.0, datetime.now().isoformat()),
        )
        for i, (sym, pnl, _marker) in enumerate(trades):
            ts = _today_ts(offset_minutes=i)
            conn.execute(
                "INSERT INTO trades (symbol, side, qty, entry_price, exit_price, pnl, pnl_pct, opened_at, closed_at, close_reason) "
                "VALUES (?, 'long', 1, 100.0, 110.0, ?, 0.1, ?, ?, 'signal_exit')",
                (sym, pnl, ts, ts),
            )
        for i, eq in enumerate(equity_points):
            ts = (datetime.now() - timedelta(hours=len(equity_points) - i - 1)).isoformat()
            conn.execute(
                "INSERT INTO equity_curve (timestamp, cash, positions_value, equity, unrealized_pl) VALUES (?, 0, 0, ?, 0)",
                (ts, eq),
            )
        conn.commit()


def test_today_trades_filters_by_midnight():
    _seed(trades=[("A", 50.0, 1), ("B", -20.0, 30)])
    trades = daily_digest._today_trades()
    syms = [t["symbol"] for t in trades]
    assert "A" in syms


def test_build_summary_shows_win_count():
    _seed(trades=[("A", 50.0, 2), ("B", -20.0, 1), ("C", 30.0, 3)])
    text = daily_digest.build_summary()
    assert "win 2" in text
    assert "loss 1" in text


def test_build_summary_equity_change(monkeypatch):
    _seed(trades=[], equity_points=[100_000, 101_500])
    monkeypatch.setattr(paper_broker, "get_account", lambda: {"equity": 101_500.0})
    text = daily_digest.build_summary()
    assert "Equity" in text


def test_send_if_due_respects_cooldown(monkeypatch, tmp_path):
    monkeypatch.setattr(daily_digest, "_state_path", lambda: tmp_path / "state.json")
    daily_digest._save_state({"last_sent_at": datetime.now().isoformat()})

    sent_messages = []

    async def fake_send(text, parse_mode="Markdown"):
        sent_messages.append(text)
        return True

    monkeypatch.setattr(daily_digest.notifier, "send_telegram", fake_send)

    result = asyncio.run(daily_digest.send_if_due(min_hours=20))
    assert result is False
    assert sent_messages == []


def test_send_if_due_sends_after_cooldown(monkeypatch, tmp_path):
    monkeypatch.setattr(daily_digest, "_state_path", lambda: tmp_path / "state.json")
    old_ts = (datetime.now() - timedelta(hours=25)).isoformat()
    daily_digest._save_state({"last_sent_at": old_ts})

    sent_messages = []

    async def fake_send(text, parse_mode="Markdown"):
        sent_messages.append(text)
        return True

    monkeypatch.setattr(daily_digest.notifier, "send_telegram", fake_send)

    result = asyncio.run(daily_digest.send_if_due(min_hours=20))
    assert result is True
    assert len(sent_messages) == 1


def test_force_send_bypasses_cooldown(monkeypatch, tmp_path):
    monkeypatch.setattr(daily_digest, "_state_path", lambda: tmp_path / "state.json")
    sent_messages = []

    async def fake_send(text, parse_mode="Markdown"):
        sent_messages.append(text)
        return True

    monkeypatch.setattr(daily_digest.notifier, "send_telegram", fake_send)

    result = asyncio.run(daily_digest.force_send())
    assert result is True
    assert len(sent_messages) == 1
