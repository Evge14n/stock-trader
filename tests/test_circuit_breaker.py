from datetime import datetime

from agents.python import paper_broker
from agents.python.circuit_breaker import check_drawdown, is_trading_hours, should_block_trading


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
