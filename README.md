# Stock Trader — Multi-Agent AI Trading System

Локальна мульти-агентна система для аналізу акцій та paper trading з Gemma 4 E2B.

## Архітектура

**14 агентів** на живих даних:

### LLM-агенти (Gemma 4 E2B через Ollama)
- `technical_analyst` — інтерпретує технічні індикатори
- `news_analyst` — sentiment новин
- `sector_analyst` — секторний контекст (tech/finance/healthcare/energy/consumer)
- `researcher` — синтезує всі аналізи
- `trader` — фінальне торгове рішення

### Python-агенти (детерміновані)
- `data_collector` — OHLCV з yfinance
- `news_fetcher` — новини + sentiment з Finnhub
- `indicators` — RSI, MACD, BB, ATR, VWAP, OBV, Stochastic, ADX, SMA50/200
- `watchlist_scanner` — фільтрує топ можливості
- `risk_validator` — 8 перевірок ризику
- `paper_broker` — локальний SQLite симулятор ($100k стартовий капітал)
- `order_manager` — виконання ордерів
- `portfolio_tracker` — P&L, статистика

## Pipeline (LangGraph)

```
collect_data → collect_news → indicators → filter_watchlist
    → technical → news → sector → research
    → trade_decision → risk_check → execute
```

## Запуск

```bash
python main.py check          # перевірка компонентів
python main.py run --dry-run  # аналіз без торгівлі
python main.py run            # аналіз + paper trading
python main.py loop           # автоматичний цикл
python main.py status         # портфель і статистика
```

## Налаштування (`.env`)

```
FINNHUB_API_KEY=your_key      # https://finnhub.io/register
OLLAMA_MODEL=gemma4:e2b
WATCHLIST=AAPL,MSFT,GOOGL,AMZN,NVDA,META,TSLA,AMD,NFLX,INTC
MAX_POSITION_SIZE=1000
RISK_PER_TRADE=0.02
```

## Залежності

- Python 3.13+
- Ollama + Gemma 4 E2B (`ollama pull gemma4:e2b`)
- GPU: GTX 1660 Super 6GB VRAM (мінімум)
