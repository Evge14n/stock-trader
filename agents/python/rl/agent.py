from __future__ import annotations

from pathlib import Path

import structlog

from agents.python.indicators import _to_df
from agents.python.rl import ACTION_BUY, ACTION_SELL
from agents.python.rl.features import observation
from config.settings import settings
from core.state import PipelineState, TradeSignal

log = structlog.get_logger(__name__)

_MODEL = None
_MODEL_LOADED = False
_MODEL_PATH: Path | None = None


def _rl_model_path() -> Path:
    return settings.data_dir / "rl" / "ppo_latest.zip"


def _load_model():
    global _MODEL, _MODEL_LOADED, _MODEL_PATH
    if _MODEL_LOADED:
        return _MODEL

    path = _rl_model_path()
    _MODEL_LOADED = True
    _MODEL_PATH = path

    if not path.exists():
        log.warning("rl_model_missing", path=str(path))
        return None

    try:
        from stable_baselines3 import PPO
    except ImportError:
        log.warning("rl_deps_missing")
        return None

    try:
        _MODEL = PPO.load(str(path))
        log.info("rl_model_loaded", path=str(path))
    except Exception as e:
        log.warning("rl_model_load_failed", error=str(e))
        _MODEL = None
    return _MODEL


def reset_cache() -> None:
    global _MODEL, _MODEL_LOADED, _MODEL_PATH
    _MODEL = None
    _MODEL_LOADED = False
    _MODEL_PATH = None


def _position_for(state: PipelineState, symbol: str) -> tuple[bool, float, int]:
    from agents.python import paper_broker

    try:
        positions = paper_broker.list_positions()
    except Exception:
        return False, 0.0, 0

    for p in positions:
        if p.get("symbol") == symbol:
            return True, float(p.get("avg_entry", 0.0)), 0
    return False, 0.0, 0


def _signal_for(symbol: str, state: PipelineState, model) -> TradeSignal | None:
    md = state.market_data.get(symbol)
    if not md or md.price <= 0 or not md.ohlcv:
        return None

    df = _to_df(md.ohlcv)
    if df.empty or len(df) < 30:
        return None

    has_pos, entry_price, holding = _position_for(state, symbol)
    obs = observation(
        df,
        idx=len(df) - 1,
        has_position=has_pos,
        entry_price=entry_price,
        holding_bars=holding,
    )

    action, _ = model.predict(obs, deterministic=True)
    action_int = int(action)

    indicators = state.indicators.get(symbol, [])
    atr_ind = next((i for i in indicators if i.name == "ATR"), None)
    atr_value = atr_ind.value if atr_ind else 0.0

    if atr_value > 0:
        atr_pct = atr_value / md.price
        stop_pct = max(0.015, min(0.05, atr_pct * 1.5))
        tp_pct = max(0.03, min(0.12, atr_pct * 3.0))
    else:
        stop_pct = 0.03
        tp_pct = 0.06

    if action_int == ACTION_BUY and not has_pos:
        risk_amount = settings.max_position_size * settings.risk_per_trade
        risk_per_share = md.price * stop_pct
        if risk_per_share <= 0:
            return None
        qty = int(risk_amount / risk_per_share)
        max_shares = int(settings.max_position_size / md.price)
        qty = min(qty, max_shares)
        if qty <= 0:
            return None
        sl = round(md.price * (1 - stop_pct), 2)
        tp = round(md.price * (1 + tp_pct), 2)
        return TradeSignal(
            symbol=symbol,
            action="buy",
            quantity=qty,
            entry_price=md.price,
            stop_loss=sl,
            take_profit=tp,
            confidence=0.7,
            reasoning="rl_ppo: buy",
        )

    if action_int == ACTION_SELL and has_pos:
        positions = []
        try:
            from agents.python import paper_broker

            positions = paper_broker.list_positions()
        except Exception:
            return None
        current = next((p for p in positions if p.get("symbol") == symbol), None)
        if not current:
            return None
        qty = int(current.get("qty", 0))
        if qty <= 0:
            return None
        sl = round(md.price * (1 + stop_pct), 2)
        tp = round(md.price * (1 - tp_pct), 2)
        return TradeSignal(
            symbol=symbol,
            action="sell",
            quantity=qty,
            entry_price=md.price,
            stop_loss=sl,
            take_profit=tp,
            confidence=0.7,
            reasoning="rl_ppo: close long",
        )

    return None


async def decide(state: PipelineState) -> PipelineState:
    model = _load_model()
    if model is None:
        state.add_error("rl_agent: no model available, skipping")
        return state

    for symbol in state.symbols:
        try:
            signal = _signal_for(symbol, state, model)
            if signal:
                state.signals.append(signal)
        except Exception as e:
            state.add_error(f"rl_agent [{symbol}]: {type(e).__name__}: {e}")
    return state


def is_available() -> bool:
    return _load_model() is not None
