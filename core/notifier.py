from __future__ import annotations

import httpx
import orjson

from config.settings import settings


async def send_telegram(text: str, parse_mode: str = "Markdown") -> bool:
    token = settings.telegram_bot_token
    chat_id = settings.telegram_chat_id

    if not token or not chat_id:
        return False

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                content=orjson.dumps(
                    {
                        "chat_id": chat_id,
                        "text": text,
                        "parse_mode": parse_mode,
                        "disable_web_page_preview": True,
                    }
                ),
                headers={"Content-Type": "application/json"},
            )
            return resp.status_code == 200
    except Exception:
        return False


async def notify_trade(
    symbol: str, action: str, qty: int, price: float, sl: float, tp: float, confidence: float, reasoning: str = ""
) -> bool:
    emoji = "🟢" if action == "buy" else "🔴"
    risk_pct = abs(price - sl) / price * 100 if price else 0.0
    reward_pct = abs(tp - price) / price * 100 if price else 0.0

    text = (
        f"{emoji} *{action.upper()} {symbol}*\n\n"
        f"Quantity: `{qty}`\n"
        f"Entry: `${price:.2f}`\n"
        f"Stop: `${sl:.2f}` ({risk_pct:.1f}%)\n"
        f"Target: `${tp:.2f}` ({reward_pct:.1f}%)\n"
        f"Confidence: `{confidence:.0%}`\n"
    )
    if reasoning:
        text += f"\n_{reasoning[:200]}_"

    return await send_telegram(text)


async def notify_cycle_summary(
    cycle_id: str, analyses_count: int, signals_count: int, executed_count: int, errors_count: int, duration_sec: float
) -> bool:
    status = "✅" if errors_count == 0 else "⚠️"
    text = (
        f"{status} *Cycle {cycle_id}*\n\n"
        f"Analyses: `{analyses_count}`\n"
        f"Signals: `{signals_count}`\n"
        f"Executed: `{executed_count}`\n"
        f"Errors: `{errors_count}`\n"
        f"Duration: `{duration_sec:.0f}s`"
    )
    return await send_telegram(text)


async def notify_error(message: str) -> bool:
    return await send_telegram(f"❌ *Stock Trader error*\n\n```\n{message[:500]}\n```")
