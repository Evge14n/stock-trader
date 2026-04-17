from core.state import (
    Analysis,
    Indicator,
    MarketData,
    PipelineState,
    RiskCheck,
    TradeSignal,
)


def test_pipeline_state_defaults():
    ps = PipelineState()
    assert ps.cycle_id == ""
    assert ps.symbols == []
    assert ps.market_data == {}
    assert ps.errors == []
    assert ps.dry_run is False


def test_add_error_timestamps():
    ps = PipelineState()
    ps.add_error("test error")
    assert len(ps.errors) == 1
    assert "test error" in ps.errors[0]


def test_market_data_fields():
    md = MarketData(symbol="AAPL", price=150.0, volume=1000)
    assert md.symbol == "AAPL"
    assert md.price == 150.0
    assert md.ohlcv == []


def test_indicator_default():
    ind = Indicator(name="RSI", value=45.0, signal="neutral")
    assert ind.name == "RSI"
    assert ind.details == {}


def test_analysis_structure():
    a = Analysis(agent="technical", symbol="AAPL", signal="bullish", confidence=0.8)
    assert a.signal == "bullish"
    assert a.confidence == 0.8


def test_trade_signal_default_values():
    sig = TradeSignal(symbol="AAPL", action="buy", quantity=10, entry_price=150.0)
    assert sig.stop_loss == 0.0
    assert sig.take_profit == 0.0


def test_risk_check_fields():
    rc = RiskCheck(passed=True, reason="ok", checks={"a": 1})
    assert rc.passed is True
    assert rc.checks == {"a": 1}
