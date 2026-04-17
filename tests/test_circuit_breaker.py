from datetime import datetime, timedelta

from agents.python import paper_broker
from agents.python.circuit_breaker import (
    check_drawdown,
    check_loss_streak,
    is_trading_hours,
    should_block_trading,
)


def _seed_equity(points: list[float]):
    import sqlite3

    with sqlite3.connect(paper_broker._db_path()) as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS equity_curve (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT NOT NULL, cash REAL NOT NULL, positions_value REAL NOT NULL, equity REAL NOT NULL, unrealized_pl REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS account (id INTEGER PRIMARY KEY CHECK (id = 1), cash REAL NOT NULL, initial_deposit REAL NOT NULL, created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS positions (symbol TEXT PRIMARY KEY, qty INTEGER NOT NULL, avg_entry REAL NOT NULL, stop_loss REAL, take_profit REAL, opened_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS trades (id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT NOT NULL, side TEXT NOT NULL, qty INTEGER NOT NULL, entry_price REAL NOT NULL, exit_price REAL, pnl REAL, pnl_pct REAL, opened_at TEXT NOT NULL, closed_at TEXT, close_reason TEXT);
        """)
        for val in points:
            conn.execute(
                "INSERT INTO equity_curve (timestamp, cash, positions_value, equity, unrealized_pl) VALUES (?, 0, 0, ?, 0)",
                (datetime.now().isoformat(), val),
            )
        conn.commit()


def test_check_drawdown_no_history():
    result = check_drawdown()
    assert result["tripped"] is False


def test_check_drawdown_no_drawdown():
    _seed_equity([100_000, 100_500, 101_000])
    result = check_drawdown(threshold_pct=10.0)
    assert result["tripped"] is False
    assert result["current_dd_pct"] == 0.0


def test_check_drawdown_5_percent():
    _seed_equity([100_000, 110_000, 104_500])
    result = check_drawdown(threshold_pct=10.0)
    assert result["tripped"] is False
    assert 4 < result["current_dd_pct"] < 6


def test_check_drawdown_tripped():
    _seed_equity([100_000, 110_000, 95_000])
    result = check_drawdown(threshold_pct=10.0)
    assert result["tripped"] is True
    assert result["current_dd_pct"] > 10


def test_is_trading_hours_structure():
    result = is_trading_hours()
    assert "is_weekend" in result
    assert "us_market_open" in result
    assert "crypto_open" in result
    assert "should_trade_stocks" in result


def test_should_block_trading_ok():
    _seed_equity([100_000, 100_500, 101_000])
    blocked, reason = should_block_trading(max_drawdown_pct=10.0)
    assert blocked is False
    assert reason == "ok"


def test_should_block_trading_drawdown():
    _seed_equity([100_000, 110_000, 90_000])
    blocked, reason = should_block_trading(max_drawdown_pct=10.0)
    assert blocked is True
    assert "circuit_breaker" in reason


def _seed_trades(pnls: list[tuple[float, int]]):
    import sqlite3

    with sqlite3.connect(paper_broker._db_path()) as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS trades (id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT NOT NULL, side TEXT NOT NULL, qty INTEGER NOT NULL, entry_price REAL NOT NULL, exit_price REAL, pnl REAL, pnl_pct REAL, opened_at TEXT NOT NULL, closed_at TEXT, close_reason TEXT);
        """)
        for pnl, age_hours in pnls:
            ts = (datetime.now() - timedelta(hours=age_hours)).isoformat()
            conn.execute(
                "INSERT INTO trades (symbol, side, qty, entry_price, pnl, opened_at, closed_at, close_reason) "
                "VALUES (?, 'long', 1, 100.0, ?, ?, ?, 'stop_loss')",
                ("X", pnl, ts, ts),
            )
        conn.commit()


def test_loss_streak_empty_returns_not_tripped():
    result = check_loss_streak()
    assert result["tripped"] is False
    assert result["streak"] == 0


def test_loss_streak_counts_from_tail():
    _seed_trades([(50, 10), (-20, 5), (-15, 3), (-30, 1)])
    result = check_loss_streak(max_consecutive=3, cooldown_hours=24)
    assert result["streak"] == 3
    assert result["tripped"] is True


def test_loss_streak_resets_on_win():
    _seed_trades([(-50, 10), (-20, 5), (30, 3), (-10, 1)])
    result = check_loss_streak(max_consecutive=3, cooldown_hours=24)
    assert result["streak"] == 1
    assert result["tripped"] is False


def test_loss_streak_cooldown_expires():
    _seed_trades([(-20, 48), (-30, 36), (-15, 30)])
    result = check_loss_streak(max_consecutive=3, cooldown_hours=24)
    assert result["streak"] == 3
    assert result["tripped"] is False


def test_should_block_trading_loss_streak(monkeypatch):
    from config.settings import settings

    monkeypatch.setattr(settings, "max_consecutive_losses", 3)
    monkeypatch.setattr(settings, "loss_cooldown_hours", 24)
    _seed_equity([100_000, 100_500])
    _seed_trades([(-20, 5), (-15, 3), (-10, 1)])
    blocked, reason = should_block_trading(max_drawdown_pct=50.0)
    assert blocked is True
    assert "consecutive losses" in reason
