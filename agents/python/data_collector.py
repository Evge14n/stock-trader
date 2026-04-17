from __future__ import annotations

import asyncio
from datetime import datetime

import finnhub
import yfinance as yf

from config.settings import settings
from core.state import MarketData, PipelineState

_finnhub_client: finnhub.Client | None = None


def _finnhub() -> finnhub.Client:
    global _finnhub_client
    if _finnhub_client is None:
        _finnhub_client = finnhub.Client(api_key=settings.finnhub_api_key)
    return _finnhub_client


def fetch_quote(symbol: str) -> dict:
    client = _finnhub()
    q = client.quote(symbol)
    return {
        "price": q.get("c", 0.0),
        "open": q.get("o", 0.0),
        "high": q.get("h", 0.0),
        "low": q.get("l", 0.0),
        "prev_close": q.get("pc", 0.0),
    }


def fetch_candles(symbol: str, period: str = "3mo", interval: str = "1d") -> list[dict]:
    ticker = yf.Ticker(symbol)
    hist = ticker.history(period=period, interval=interval, auto_adjust=False)

    if hist.empty:
        return []

    rows = []
    for idx, row in hist.iterrows():
        rows.append({
            "timestamp": int(idx.timestamp()),
            "open": float(row["Open"]),
            "high": float(row["High"]),
            "low": float(row["Low"]),
            "close": float(row["Close"]),
            "volume": int(row["Volume"]),
        })
    return rows


def fetch_market_data(symbol: str) -> MarketData:
    candles = fetch_candles(symbol)
    if not candles:
        return MarketData(symbol=symbol, timestamp=datetime.now().isoformat())

    try:
        quote = fetch_quote(symbol)
        price = quote["price"] or candles[-1]["close"]
        day_open = quote["open"] or candles[-1]["open"]
        day_high = quote["high"] or candles[-1]["high"]
        day_low = quote["low"] or candles[-1]["low"]
    except Exception:
        last = candles[-1]
        price = last["close"]
        day_open = last["open"]
        day_high = last["high"]
        day_low = last["low"]

    return MarketData(
        symbol=symbol,
        price=price,
        open=day_open,
        high=day_high,
        low=day_low,
        close=candles[-1]["close"],
        volume=candles[-1]["volume"],
        ohlcv=candles,
        timestamp=datetime.now().isoformat(),
    )


async def collect_all(state: PipelineState) -> PipelineState:
    for symbol in state.symbols:
        try:
            md = await asyncio.to_thread(fetch_market_data, symbol)
            state.market_data[symbol] = md
        except Exception as e:
            state.add_error(f"data_collector [{symbol}]: {e}")
    return state
