from __future__ import annotations

import asyncio
from datetime import datetime

from agents.python import paper_broker
from agents.python.benchmark import get_comparison
from agents.python.dashboard_data import sector_heatmap
from agents.python.macro import get_macro_summary
from core import llm_client, notifier


async def generate_daily_report() -> str:
    account = paper_broker.get_account()
    positions = paper_broker.list_positions()
    stats = paper_broker.get_trade_stats()

    try:
        benchmark = await asyncio.to_thread(get_comparison)
    except Exception:
        benchmark = {}

    try:
        macro = await asyncio.to_thread(get_macro_summary)
    except Exception:
        macro = {}

    try:
        sectors = await asyncio.to_thread(sector_heatmap)
    except Exception:
        sectors = {}

    top_sectors = list(sectors.items())[:3]

    lines = [
        f"*Daily Report — {datetime.now().strftime('%Y-%m-%d %H:%M')}*",
        "",
        f"💼 Equity: `${account['equity']:,.2f}`",
        f"💵 Cash: `${account['cash']:,.2f}`",
        f"📊 Позицій: `{len(positions)}`",
    ]

    if benchmark and not benchmark.get("error"):
        alpha = benchmark.get("alpha_pct", 0)
        emoji = "🟢" if alpha > 0 else "🔴"
        lines.append(f"{emoji} Alpha (vs SPY): `{alpha:+.2f}%`")

    if stats["total_trades"] > 0:
        lines.append(f"📈 Угод: `{stats['total_trades']}` • Win rate: `{stats['win_rate'] * 100:.0f}%`")
        lines.append(f"💰 Total P/L: `${stats['total_pnl']:+,.2f}`")

    if positions:
        lines.append("\n*Відкриті позиції:*")
        for p in positions:
            pl = p.get("unrealized_pl", 0)
            emoji = "🟢" if pl >= 0 else "🔴"
            lines.append(f"{emoji} {p['symbol']}: {p['qty']} шт @ ${p['avg_entry']:.2f} → P/L `${pl:+.2f}`")

    if macro and not macro.get("error"):
        regime = macro.get("risk_regime", "")
        regime_emoji = "🟢" if regime == "risk_on" else "🔴" if regime == "risk_off" else "🟡"
        lines.append(f"\n*Макро:* {regime_emoji} {regime}")
        lines.append(f"VIX: `{macro.get('vix', 0):.1f}` • 10Y: `{macro.get('treasury_10y', 0):.2f}%`")

    if top_sectors:
        lines.append("\n*Топ сектори:*")
        for sec, info in top_sectors:
            emoji = "🟢" if info["avg_change_pct"] > 0 else "🔴"
            lines.append(f"{emoji} {sec}: `{info['avg_change_pct']:+.2f}%`")

    ai_commentary = await _generate_ai_commentary(account, positions, stats, macro, sectors)
    if ai_commentary:
        lines.append(f"\n*AI прогноз:*\n_{ai_commentary}_")

    return "\n".join(lines)


async def _generate_ai_commentary(account: dict, positions: list[dict], stats: dict, macro: dict, sectors: dict) -> str:
    system = """You are a senior portfolio manager writing a 2-3 sentence daily briefing for a swing trader.
Focus on: market conditions, portfolio risk, what to watch tomorrow. Be concise and actionable. Avoid generic advice."""

    context = f"""Portfolio: ${account.get("equity", 0):,.0f}, {len(positions)} positions, {stats.get("total_trades", 0)} total trades, {stats.get("win_rate", 0) * 100:.0f}% win rate.
Market regime: {macro.get("risk_regime", "unknown")}. VIX: {macro.get("vix", 0):.1f}. 10Y yield: {macro.get("treasury_10y", 0):.2f}%.
Positions: {", ".join([p["symbol"] for p in positions]) if positions else "none"}.
Top sectors today: {", ".join([f"{s} {d['avg_change_pct']:+.1f}%" for s, d in list(sectors.items())[:3]]) if sectors else "n/a"}."""

    try:
        response = await llm_client.query(
            prompt=context,
            system=system,
            temperature=0.4,
            max_tokens=200,
        )
        return response[:400]
    except Exception:
        return ""


async def send_daily_report() -> bool:
    report = await generate_daily_report()
    return await notifier.send_telegram(report)


class DailyScheduler:
    def __init__(self, hour: int = 20, minute: int = 0):
        self.hour = hour
        self.minute = minute
        self.running = False
        self._last_sent_date: str = ""

    async def run(self):
        self.running = True
        while self.running:
            now = datetime.now()
            today = now.strftime("%Y-%m-%d")

            if (
                now.hour > self.hour or (now.hour == self.hour and now.minute >= self.minute)
            ) and self._last_sent_date != today:
                await send_daily_report()
                self._last_sent_date = today

            await asyncio.sleep(60)

    def stop(self):
        self.running = False


_scheduler: DailyScheduler | None = None


def get_scheduler() -> DailyScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = DailyScheduler()
    return _scheduler
