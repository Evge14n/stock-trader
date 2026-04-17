from __future__ import annotations

from datetime import datetime

from agents.python import paper_broker
from core.state import PipelineState


def get_account_info() -> dict:
    acc = paper_broker.get_account()
    return {
        "equity": acc["equity"],
        "cash": acc["cash"],
        "buying_power": acc["buying_power"],
        "portfolio_value": acc["equity"],
        "day_trade_count": 0,
    }


def get_positions() -> list[dict]:
    return paper_broker.list_positions()


def get_positions_with_prices(prices: dict[str, float]) -> list[dict]:
    return paper_broker.list_positions(prices)


def submit_order(symbol: str, qty: int, side: str, price: float,
                 stop_loss: float | None = None, take_profit: float | None = None,
                 confidence: float = 0.0, reasoning: str = "") -> dict:
    return paper_broker.submit_order(
        symbol=symbol,
        qty=qty,
        side=side,
        price=price,
        stop_loss=stop_loss,
        take_profit=take_profit,
        confidence=confidence,
        reasoning=reasoning,
    )


async def execute_trades(state: PipelineState) -> PipelineState:
    current_prices = {sym: md.price for sym, md in state.market_data.items()}

    triggered = paper_broker.check_stop_targets(current_prices)
    for r in triggered:
        r["trigger"] = "auto_close"
        state.execution_results.append(r)

    for signal in state.approved_trades:
        try:
            md = state.market_data.get(signal.symbol)
            price = md.price if md else signal.entry_price
            result = submit_order(
                symbol=signal.symbol,
                qty=signal.quantity,
                side=signal.action,
                price=price,
                stop_loss=signal.stop_loss,
                take_profit=signal.take_profit,
                confidence=signal.confidence,
                reasoning=signal.reasoning,
            )
            result["executed_at"] = datetime.now().isoformat()
            state.execution_results.append(result)
        except Exception as e:
            state.add_error(f"order_manager [{signal.symbol}]: {e}")

    paper_broker.record_equity(current_prices)
    return state
