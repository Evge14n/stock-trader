from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

import finnhub

from config.settings import settings
from core.state import NewsItem, PipelineState

_client: finnhub.Client | None = None


def _get_client() -> finnhub.Client:
    global _client
    if _client is None:
        _client = finnhub.Client(api_key=settings.finnhub_api_key)
    return _client


def fetch_news(symbol: str, days: int = 3) -> list[NewsItem]:
    client = _get_client()
    today = datetime.now().strftime("%Y-%m-%d")
    from_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

    raw = client.company_news(symbol, _from=from_date, to=today)
    items = []
    for article in raw[:10]:
        items.append(
            NewsItem(
                headline=article.get("headline", ""),
                source=article.get("source", ""),
                url=article.get("url", ""),
                sentiment=0.0,
                timestamp=datetime.fromtimestamp(article.get("datetime", 0)).isoformat(),
            )
        )
    return items


def fetch_sentiment(symbol: str) -> dict:
    client = _get_client()
    try:
        data = client.news_sentiment(symbol)
        buzz = data.get("buzz", {})
        sentiment = data.get("sentiment", {})
        return {
            "articles_in_week": buzz.get("articlesInLastWeek", 0),
            "buzz_score": buzz.get("buzz", 0.0),
            "bullish": sentiment.get("bullishPercent", 0.0),
            "bearish": sentiment.get("bearishPercent", 0.0),
            "overall": sentiment.get("companyNewsScore", 0.0),
        }
    except Exception:
        return {}


async def collect_news(state: PipelineState) -> PipelineState:
    for symbol in state.symbols:
        try:
            news = fetch_news(symbol)
            api_sentiment = fetch_sentiment(symbol)

            for item in news:
                if api_sentiment:
                    item.sentiment = api_sentiment.get("overall", 0.0)

            state.news[symbol] = news
            await asyncio.sleep(0.3)
        except Exception as e:
            state.add_error(f"news_fetcher [{symbol}]: {e}")
    return state
