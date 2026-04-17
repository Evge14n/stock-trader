from __future__ import annotations

from datetime import datetime

from agents.python import paper_broker
from core import notifier
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


def submit_order(
    symbol: str,
    qty: int,
    side: str,
    price: float,
    stop_loss: float | None = None,
    take_profit: float | None = None,
    confidence: float = 0.0,
    reasoning: str = "",
) -> dict:
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


def _find_researcher_signal(symbol: str, state: PipelineState) -> tuple[str, float] | None:
    analyses = state.analyses.get(symbol, [])
    for a in reversed(analyses):
        if a.agent == "researcher":
            return a.signal, a.confidence
    return None


async def _close_on_signal_reversal(state: PipelineState, current_prices: dict[str, float]) -> list[dict]:
    closed = []
    held = paper_broker.list_positions()

    for pos in held:
        sym = pos["symbol"]
        signal_info = _find_researcher_signal(sym, state)
        if not signal_info:
            continue

        signal, confidence = signal_info
        bearish = signal in ("sell", "strong_sell", "bearish")
        if bearish and confidence >= 0.6:
            price = current_prices.get(sym, pos["avg_entry"])
            result = paper_broker.submit_order(sym, pos["qty"], "sell", price)
            result["close_reason"] = "signal_reversal"
            result["trigger"] = "auto_close"
            closed.append(result)

            if result.get("status") == "filled":
                await notifier.send_telegram(
                    f"🔄 *Exit on reversal: {sym}*\n\n"
                    f"Qty: `{pos['qty']}`\n"
                    f"Price: `${price:.2f}`\n"
                    f"Researcher flipped: `{signal}` ({confidence:.0%})"
                )

    return closed


async def execute_trades(state: PipelineState) -> PipelineState:
    current_prices = {sym: md.price for sym, md in state.market_data.items()}

    paper_broker.update_trailing_stops(current_prices, trail_pct=0.03)
    triggered = paper_broker.check_stop_targets(current_prices)
    for r in triggered:
        r["trigger"] = "auto_close"
        state.execution_results.append(r)

    reversal_closed = await _close_on_signal_reversal(state, current_prices)
    for r in reversal_closed:
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

            if result.get("status") == "filled":
                await notifier.notify_trade(
                    symbol=signal.symbol,
                    action=signal.action,
                    qty=signal.quantity,
                    price=price,
                    sl=signal.stop_loss,
                    tp=signal.take_profit,
                    confidence=signal.confidence,
                    reasoning=signal.reasoning,
                )
        except Exception as e:
            state.add_error(f"order_manager [{signal.symbol}]: {e}")

    paper_broker.record_equity(current_prices)
    return state
