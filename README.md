# Stock Trader

[![CI](https://github.com/Evge14n/stock-trader/actions/workflows/ci.yml/badge.svg)](https://github.com/Evge14n/stock-trader/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Code style: Ruff](https://img.shields.io/badge/code%20style-ruff-blue.svg)](https://github.com/astral-sh/ruff)

Multi-agent AI trading system що використовує локальну LLM (Gemma 4 E2B) для аналізу акцій з технічного, фундаментального, секторального та новинного боку. Виконує paper trading через локальний SQLite broker.

## Можливості

- **14 спеціалізованих агентів** у пайплайні LangGraph
- **6 LLM-агентів** паралельно на Gemma 4 E2B (technical, news, sector, fundamental, momentum, volatility)
- **8 Python-агентів** для даних, індикаторів, ризик-менеджменту та виконання
- **Backtest engine** з реальною історією через yfinance
- **Live dashboard** на FastAPI + Chart.js (темна тема)
- **Paper broker** локально в SQLite ($100k стартовий капітал)
- **Повна ізоляція** — все працює локально, жодних зовнішніх брокерів

## Архітектура пайплайну

```
┌──────────────┐   ┌──────────────┐   ┌──────────────────┐
│ collect_data │──>│ collect_news │──>│ compute_indicators│
└──────────────┘   └──────────────┘   └──────────┬───────┘
                                                 │
                                                 ▼
                                        ┌──────────────┐
                                        │ filter_watchlist
                                        └──────┬───────┘
                                               │
                                               ▼
            ┌───────────────────┬──────────────┬───────────────┐
            │                   │              │               │
            ▼                   ▼              ▼               ▼
    ┌──────────────┐    ┌──────────────┐ ┌──────────┐ ┌──────────────┐
    │  technical   │    │    news      │ │  sector  │ │ fundamental  │
    │   analyst    │    │   analyst    │ │ analyst  │ │   analyst    │
    └──────┬───────┘    └──────┬───────┘ └─────┬────┘ └──────┬───────┘
           │                   │               │              │
           └────────┬──────────┴───────┬───────┴──────────────┘
                    ▼                   ▼
            ┌──────────────┐    ┌──────────────┐
            │  momentum    │    │ volatility   │
            │  analyst     │    │  analyst     │
            └──────┬───────┘    └──────┬───────┘
                   └──────────┬────────┘
                              ▼
                    ┌──────────────────┐
                    │  researcher      │ (синтез всіх)
                    └────────┬─────────┘
                             ▼
                    ┌──────────────────┐
                    │     trader       │ (рішення)
                    └────────┬─────────┘
                             ▼
                    ┌──────────────────┐
                    │  risk_validator  │
                    └────────┬─────────┘
                             ▼
                    ┌──────────────────┐
                    │    execute       │
                    └──────────────────┘
```

## Встановлення

### Вимоги
- Python 3.12+
- Ollama ([download](https://ollama.com/download))
- GPU: мінімум 6GB VRAM (для Gemma 4 E2B)
- 10GB вільного місця

### Swift setup

```bash
git clone https://github.com/Evge14n/stock-trader.git
cd stock-trader

python -m venv .venv
.venv\Scripts\activate              # Windows
source .venv/bin/activate           # Linux/Mac

pip install -r requirements.txt

ollama pull gemma4:e2b

cp .env.example .env
```

Далі зареєструйся на [finnhub.io](https://finnhub.io/register) (безкоштовно) та встав ключ в `.env`:

```env
FINNHUB_API_KEY=твій_ключ
```

### Docker setup

```bash
cp .env.example .env
docker-compose up -d
docker exec -it stock-trader-ollama ollama pull gemma4:e2b
```

## Використання

### CLI команди

```bash
python main.py check           # перевірка залежностей
python main.py run             # один цикл аналізу + торгівлі
python main.py run --dry-run   # аналіз без торгівлі
python main.py loop            # безперервний режим (кожну годину)
python main.py status          # поточний стан портфеля
python main.py backtest        # історичне тестування
python main.py dashboard       # запустити web-панель
python main.py reset           # скинути портфель до $100k
```

### Web Dashboard

```bash
python main.py dashboard
```

Відкрий [http://localhost:8000](http://localhost:8000). Вкладки:
- **Огляд** — капітал, крива, основні метрики
- **Позиції** — відкриті позиції з live P/L
- **Угоди** — історія всіх закритих угод
- **Аналіз агентів** — останні висновки від LLM
- **Ринок** — 10 акцій з реальними цінами
- **Активність** — журнал подій пайплайну

### Backtest приклад

```bash
python main.py backtest --period 1y
```

Вивід:
```
┌─────────────────┬─────────────┐
│ Metric          │       Value │
├─────────────────┼─────────────┤
│ Initial Capital │ $100,000.00 │
│ Final Capital   │ $108,254.20 │
│ Total Pnl       │   $8,254.20 │
│ Total Pnl Pct   │      +8.25% │
│ Total Trades    │         102 │
│ Win Rate        │     +37.25% │
│ Max Drawdown    │     +13.45% │
│ Sharpe Ratio    │        0.90 │
└─────────────────┴─────────────┘
```

## Налаштування

Всі параметри в `.env`:

| Змінна | За замовчуванням | Опис |
|---|---|---|
| `FINNHUB_API_KEY` | — | Ключ Finnhub для новин |
| `OLLAMA_MODEL` | `gemma4:e2b` | Модель Ollama |
| `WATCHLIST` | 10 тикерів | Список акцій через кому |
| `MAX_POSITION_SIZE` | 1000 | Макс $ на позицію |
| `MAX_TOTAL_EXPOSURE` | 5000 | Макс $ загалом у позиціях |
| `RISK_PER_TRADE` | 0.02 | Ризик на угоду (2%) |
| `CYCLE_INTERVAL_SEC` | 3600 | Інтервал loop-режиму |

## Розробка

### Тести
```bash
pytest tests/ -v                        # всі тести
pytest tests/ --cov=agents --cov=core   # з покриттям
```

### Лінтинг
```bash
ruff check .
ruff format .
mypy agents core config
```

### Pre-commit hooks
```bash
pip install pre-commit
pre-commit install
```

## Структура проекту

```
stock-trader/
├── agents/
│   ├── llm/                     # LLM-агенти (Gemma 4)
│   │   ├── technical_analyst.py
│   │   ├── news_analyst.py
│   │   ├── sector_analyst.py
│   │   ├── fundamental_analyst.py
│   │   ├── momentum_analyst.py
│   │   ├── volatility_analyst.py
│   │   ├── researcher.py
│   │   └── trader.py
│   └── python/                  # Детерміновані агенти
│       ├── data_collector.py
│       ├── news_fetcher.py
│       ├── indicators.py        # RSI, MACD, BB, ATR, VWAP, OBV, ADX, Stochastic
│       ├── watchlist_scanner.py
│       ├── risk_validator.py    # 8 перевірок ризику
│       ├── order_manager.py
│       ├── paper_broker.py      # SQLite paper trading
│       ├── portfolio_tracker.py
│       └── backtest.py
├── core/
│   ├── state.py                 # Dataclasses для стану пайплайну
│   ├── llm_client.py            # Ollama HTTP клієнт + кеш
│   └── orchestrator.py          # LangGraph StateGraph
├── config/
│   └── settings.py              # Pydantic settings з .env
├── dashboard/
│   ├── server.py                # FastAPI backend
│   └── static/
│       ├── index.html
│       ├── style.css
│       └── app.js
├── tests/                       # 38 pytest тестів
├── main.py                      # CLI entry point
├── pyproject.toml               # ruff + mypy + pytest config
├── Dockerfile
└── docker-compose.yml
```

## Ліцензія

MIT

## Автор

Olga Martynyuk
