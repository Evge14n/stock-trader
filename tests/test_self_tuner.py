from datetime import datetime, timedelta
from unittest.mock import patch

from agents.python.self_tuner import _analyze_trades, reset_tuner, run_tuning_cycle


def _trade(pnl: float, reason: str = "take_profit", days_ago: int = 1) -> dict:
    closed = (datetime.now() - timedelta(days=days_ago)).isoformat()
    return {
        "symbol": "AAPL",
        "pnl": pnl,
        "close_reason": reason,
        "closed_at": closed,
    }


def test_analyze_empty_trades():
    result = _analyze_trades([])
    assert result["count"] == 0
    assert result["suggestions"] == []


def test_analyze_low_win_rate_suggests_higher_confidence():
    trades = [_trade(-50), _trade(-30), _trade(100), _trade(-20), _trade(-40), _trade(-10)]
    result = _analyze_trades(trades)
    suggestions = {s["param"]: s for s in result["suggestions"]}
    assert "confidence_threshold" in suggestions


def test_analyze_bad_reward_risk_widens_tp():
    trades = [_trade(50), _trade(-200), _trade(30), _trade(-150)]
    result = _analyze_trades(trades)
    assert any(s["param"] == "take_profit_multiplier" for s in result["suggestions"])


def test_analyze_many_stop_losses_widens_sl():
    trades = [_trade(-50, "stop_loss") for _ in range(5)] + [_trade(100, "take_profit")]
    result = _analyze_trades(trades)
    assert any(s["param"] == "stop_loss_multiplier" for s in result["suggestions"])


def test_run_tuning_cycle_no_trades():
    reset_tuner()
    with patch("agents.python.self_tuner._load_recent_trades", return_value=[]):
        result = run_tuning_cycle(force=True)
    assert result["status"] == "no_changes_needed"


def test_run_tuning_cycle_skips_if_recent():
    reset_tuner()
    with patch("agents.python.self_tuner._load_recent_trades", return_value=[]):
        run_tuning_cycle(force=True)
        second = run_tuning_cycle(force=False)
    assert second["status"] == "skipped"


def test_run_tuning_cycle_with_suggestions():
    reset_tuner()
    trades = [_trade(-50) for _ in range(6)]
    with patch("agents.python.self_tuner._load_recent_trades", return_value=trades):
        result = run_tuning_cycle(force=True)
    assert result["status"] == "applied"
    assert result["adjustment"]["applied"]
