from __future__ import annotations

from datetime import datetime, timedelta

import finnhub
import yfinance as yf

from agents.llm.sector_analyst import SECTORS
from agents.python import paper_broker
from config.settings import settings

_fn_client: finnhub.Client | None = None


def _finnhub() -> finnhub.Client:
    global _fn_client
    if _fn_client is None:
        _fn_client = finnhub.Client(api_key=settings.finnhub_api_key)
    return _fn_client


def fetch_live_news(max_per_symbol: int = 3, symbols: list[str] | None = None) -> list[dict]:
    symbols = symbols or settings.symbols[:10]
    news_items: list[dict] = []
    client = _finnhub()

    today = datetime.now().strftime("%Y-%m-%d")
    from_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    for sym in symbols:
        try:
            raw = client.company_news(sym, _from=from_date, to=today)
            for article in raw[:max_per_symbol]:
                news_items.append(
                    {
                        "symbol": sym,
                        "headline": article.get("headline", ""),
                        "source": article.get("source", ""),
                        "url": article.get("url", ""),
                        "timestamp": datetime.fromtimestamp(article.get("datetime", 0)).isoformat(),
                        "image": article.get("image", ""),
                    }
                )
        except Exception:
            continue

    news_items.sort(key=lambda x: x["timestamp"], reverse=True)
    return news_items[:30]


def _yf_change_pct(sym: str) -> float | None:
    try:
        hist = yf.Ticker(sym).history(period="5d", interval="1d")
        if hist.empty or len(hist) < 2:
            return None
        return float((hist["Close"].iloc[-1] - hist["Close"].iloc[-2]) / hist["Close"].iloc[-2] * 100)
    except Exception:
        return None


def sector_heatmap() -> dict:
    sectors_perf: dict[str, dict] = {}

    for sector, stocks in SECTORS.items():
        watchlist_stocks = [s for s in stocks if s in settings.symbols]
        if not watchlist_stocks:
            continue

        changes = []
        details = []
        for sym in watchlist_stocks[:5]:
            ch = _yf_change_pct(sym)
            if ch is not None:
                changes.append(ch)
                details.append({"symbol": sym, "change_pct": round(ch, 2)})

        if not changes:
            continue

        avg_change = sum(changes) / len(changes)
        sectors_perf[sector] = {
            "avg_change_pct": round(avg_change, 2),
            "stocks": details,
            "count": len(changes),
        }

    sorted_sectors = sorted(sectors_perf.items(), key=lambda x: x[1]["avg_change_pct"], reverse=True)
    return dict(sorted_sectors)


def portfolio_allocation() -> dict:
    positions = paper_broker.list_positions()
    account = paper_broker.get_account()

    total_value = account["cash"] + sum(p["qty"] * p["avg_entry"] for p in positions)

    breakdown = {
        "cash": {
            "value": round(account["cash"], 2),
            "pct": round(account["cash"] / total_value * 100, 2) if total_value else 0,
        }
    }

    sector_totals: dict[str, float] = {}
    position_details = []

    for p in positions:
        value = p["qty"] * p["avg_entry"]
        sector = "unknown"
        for sec, symbols in SECTORS.items():
            if p["symbol"] in symbols:
                sector = sec
                break

        sector_totals[sector] = sector_totals.get(sector, 0) + value
        position_details.append(
            {
                "symbol": p["symbol"],
                "sector": sector,
                "value": round(value, 2),
                "pct": round(value / total_value * 100, 2) if total_value else 0,
            }
        )

    sectors_pct = {
        sec: {"value": round(val, 2), "pct": round(val / total_value * 100, 2) if total_value else 0}
        for sec, val in sector_totals.items()
    }

    return {
        "total_value": round(total_value, 2),
        "cash": breakdown["cash"],
        "positions": position_details,
        "by_sector": sectors_pct,
    }
