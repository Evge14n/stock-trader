import pytest

from agents.python import paper_broker


def test_initial_account():
    acc = paper_broker.get_account()
    assert acc["cash"] == 100_000.0
    assert acc["initial_deposit"] == 100_000.0
    assert acc["equity"] == 100_000.0


def test_buy_order_reduces_cash():
    result = paper_broker.submit_order("AAPL", 10, "buy", 150.0)
    assert result["status"] == "filled"

    acc = paper_broker.get_account()
    assert acc["cash"] == 100_000.0 - 10 * 150.0


def test_buy_creates_position():
    paper_broker.submit_order("AAPL", 10, "buy", 150.0)
    positions = paper_broker.list_positions()
    assert len(positions) == 1
    assert positions[0]["symbol"] == "AAPL"
    assert positions[0]["qty"] == 10


def test_sell_closes_position_and_records_trade():
    paper_broker.submit_order("AAPL", 10, "buy", 150.0)
    result = paper_broker.submit_order("AAPL", 10, "sell", 160.0)

    assert result["status"] == "filled"
    assert paper_broker.list_positions() == []

    stats = paper_broker.get_trade_stats()
    assert stats["total_trades"] == 1
    assert stats["wins"] == 1
    assert stats["total_pnl"] == 100.0


def test_sell_losing_trade():
    paper_broker.submit_order("AAPL", 10, "buy", 150.0)
    paper_broker.submit_order("AAPL", 10, "sell", 140.0)

    stats = paper_broker.get_trade_stats()
    assert stats["losses"] == 1
    assert stats["total_pnl"] == -100.0


def test_insufficient_cash_rejected():
    result = paper_broker.submit_order("AAPL", 10000, "buy", 150.0)
    assert result["status"] == "rejected_insufficient_cash"


def test_duplicate_buy_rejected():
    paper_broker.submit_order("AAPL", 10, "buy", 150.0)
    result = paper_broker.submit_order("AAPL", 5, "buy", 155.0)
    assert result["status"] == "rejected_already_holding"


def test_sell_without_position_rejected():
    result = paper_broker.submit_order("AAPL", 10, "sell", 150.0)
    assert result["status"] == "rejected_no_position"


def test_stop_loss_triggered():
    paper_broker.submit_order(
        "AAPL", 10, "buy", 150.0,
        stop_loss=145.0, take_profit=165.0,
    )
    closed = paper_broker.check_stop_targets({"AAPL": 144.0})
    assert len(closed) == 1
    assert closed[0]["status"] == "filled"
    assert paper_broker.list_positions() == []


def test_take_profit_triggered():
    paper_broker.submit_order(
        "AAPL", 10, "buy", 150.0,
        stop_loss=145.0, take_profit=165.0,
    )
    closed = paper_broker.check_stop_targets({"AAPL": 166.0})
    assert len(closed) == 1
    assert paper_broker.list_positions() == []


def test_position_unrealized_pnl():
    paper_broker.submit_order("AAPL", 10, "buy", 150.0)
    positions = paper_broker.list_positions({"AAPL": 160.0})
    assert positions[0]["unrealized_pl"] == 100.0


def test_win_rate_calculation():
    paper_broker.submit_order("AAPL", 10, "buy", 150.0)
    paper_broker.submit_order("AAPL", 10, "sell", 160.0)
    paper_broker.submit_order("MSFT", 10, "buy", 300.0)
    paper_broker.submit_order("MSFT", 10, "sell", 290.0)
    paper_broker.submit_order("NVDA", 10, "buy", 200.0)
    paper_broker.submit_order("NVDA", 10, "sell", 210.0)

    stats = paper_broker.get_trade_stats()
    assert stats["total_trades"] == 3
    assert stats["wins"] == 2
    assert stats["losses"] == 1
    assert stats["win_rate"] == pytest.approx(2 / 3, abs=0.01)
