from __future__ import annotations

from config.settings import settings
from core.state import PipelineState, RiskCheck, TradeSignal


def _check_position_size(signal: TradeSignal) -> tuple[bool, str]:
    exposure = signal.quantity * signal.entry_price
    if exposure > settings.max_position_size:
        return False, f"position ${exposure:.0f} exceeds max ${settings.max_position_size:.0f}"
    return True, "ok"


def _check_stop_loss(signal: TradeSignal) -> tuple[bool, str]:
    if signal.action == "buy":
        risk_pct = (signal.entry_price - signal.stop_loss) / signal.entry_price
    else:
        risk_pct = (signal.stop_loss - signal.entry_price) / signal.entry_price

    if risk_pct <= 0:
        return False, "invalid stop loss placement"
    if risk_pct > 0.05:
        return False, f"stop loss {risk_pct:.1%} exceeds 5% max"
    return True, "ok"


def _check_reward_risk(signal: TradeSignal) -> tuple[bool, str]:
    if signal.action == "buy":
        risk = signal.entry_price - signal.stop_loss
        reward = signal.take_profit - signal.entry_price
    else:
        risk = signal.stop_loss - signal.entry_price
        reward = signal.entry_price - signal.take_profit

    if risk <= 0:
        return False, "zero or negative risk"
    ratio = reward / risk
    if ratio < 1.5:
        return False, f"R:R {ratio:.1f} below minimum 1.5"
    return True, "ok"


def _check_total_exposure(signal: TradeSignal, state: PipelineState) -> tuple[bool, str]:
    existing = sum(t.quantity * t.entry_price for t in state.approved_trades)
    new_exposure = signal.quantity * signal.entry_price
    total = existing + new_exposure

    if total > settings.max_total_exposure:
        return False, f"total exposure ${total:.0f} exceeds max ${settings.max_total_exposure:.0f}"
    return True, "ok"


def _check_max_positions(state: PipelineState) -> tuple[bool, str]:
    if len(state.approved_trades) >= settings.max_concurrent_positions:
        return False, f"max {settings.max_concurrent_positions} concurrent positions reached"
    return True, "ok"


def _check_duplicate(signal: TradeSignal, state: PipelineState) -> tuple[bool, str]:
    for t in state.approved_trades:
        if t.symbol == signal.symbol:
            return False, f"already have position in {signal.symbol}"
    return True, "ok"


def _check_confidence(signal: TradeSignal) -> tuple[bool, str]:
    if signal.confidence < 0.6:
        return False, f"confidence {signal.confidence:.2f} below 0.6 threshold"
    return True, "ok"


def _check_price_validity(signal: TradeSignal) -> tuple[bool, str]:
    if signal.entry_price <= 0:
        return False, "invalid entry price"
    if signal.quantity <= 0:
        return False, "invalid quantity"
    return True, "ok"


def _check_circuit_breaker(signal: TradeSignal) -> tuple[bool, str]:
    from agents.python.circuit_breaker import should_block_trading

    blocked, reason = should_block_trading(max_drawdown_pct=10.0)
    if blocked:
        return False, reason
    return True, "ok"


CHECKS = [
    ("circuit_breaker", _check_circuit_breaker),
    ("price_validity", _check_price_validity),
    ("confidence", _check_confidence),
    ("position_size", _check_position_size),
    ("stop_loss", _check_stop_loss),
    ("reward_risk", _check_reward_risk),
]

STATE_CHECKS = [
    ("total_exposure", _check_total_exposure),
    ("max_positions", lambda sig, st: _check_max_positions(st)),
    ("duplicate", _check_duplicate),
]


async def validate(state: PipelineState) -> PipelineState:
    for signal in state.signals:
        checks = {}
        passed = True

        for name, fn in CHECKS:
            ok, msg = fn(signal)
            checks[name] = {"passed": ok, "message": msg}
            if not ok:
                passed = False

        for name, fn in STATE_CHECKS:
            ok, msg = fn(signal, state)
            checks[name] = {"passed": ok, "message": msg}
            if not ok:
                passed = False

        rc = RiskCheck(passed=passed, reason="" if passed else "risk check failed", checks=checks)
        state.risk_checks.append(rc)

        if passed:
            state.approved_trades.append(signal)

    return state
