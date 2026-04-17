import pytest

from agents.python.risk_validator import validate
from core.state import PipelineState, TradeSignal


@pytest.fixture
def valid_signal():
    return TradeSignal(
        symbol="AAPL",
        action="buy",
        quantity=5,
        entry_price=150.0,
        stop_loss=145.0,
        take_profit=165.0,
        confidence=0.75,
        reasoning="strong technical setup",
    )


async def test_valid_signal_approved(valid_signal):
    state = PipelineState(signals=[valid_signal])
    state = await validate(state)

    assert len(state.approved_trades) == 1
    assert state.risk_checks[0].passed


async def test_low_confidence_rejected(valid_signal):
    valid_signal.confidence = 0.4
    state = PipelineState(signals=[valid_signal])
    state = await validate(state)

    assert len(state.approved_trades) == 0
    assert not state.risk_checks[0].passed


async def test_bad_rr_ratio_rejected(valid_signal):
    valid_signal.take_profit = 151.0
    state = PipelineState(signals=[valid_signal])
    state = await validate(state)

    assert len(state.approved_trades) == 0


async def test_oversized_stop_rejected(valid_signal):
    valid_signal.stop_loss = 140.0
    state = PipelineState(signals=[valid_signal])
    state = await validate(state)

    assert len(state.approved_trades) == 0


async def test_zero_quantity_rejected(valid_signal):
    valid_signal.quantity = 0
    state = PipelineState(signals=[valid_signal])
    state = await validate(state)

    assert len(state.approved_trades) == 0


async def test_duplicate_symbol_rejected():
    first = TradeSignal(
        symbol="AAPL",
        action="buy",
        quantity=5,
        entry_price=150.0,
        stop_loss=145.0,
        take_profit=165.0,
        confidence=0.75,
        reasoning="",
    )
    second = TradeSignal(
        symbol="AAPL",
        action="buy",
        quantity=3,
        entry_price=151.0,
        stop_loss=146.0,
        take_profit=166.0,
        confidence=0.8,
        reasoning="",
    )
    state = PipelineState(signals=[first, second])
    state = await validate(state)

    assert len(state.approved_trades) == 1
