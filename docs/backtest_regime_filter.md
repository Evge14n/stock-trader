# Regime filter impact on BB mean-reversion

Live yfinance data, 2026-04-17, 6 symbols (AAPL, MSFT, NVDA, GOOGL, AMZN, TSLA), period=1y.

| Strategy | PnL % | Trades | Win % | Sharpe | MaxDD % |
|---|---:|---:|---:|---:|---:|
| bb_mean_reversion | +17.88 | 64 | 50.0 | 2.11 | 6.61 |
| bb_regime_filtered (ADX<30) | +8.32 | 40 | 45.0 | 1.25 | 4.82 |
| bb_35 (ADX<35) | +6.23 | 49 | 40.8 | 0.88 | 6.63 |
| bb_40 (ADX<40) | +10.41 | 59 | 44.1 | 1.36 | 7.24 |

## Висновок

Regime-фільтр на основі ADX РІЖЕ прибутковість BB mean-reversion на цьому ринку. Ймовірно тому що 2025-2026 — сильний bull trend, і BB oversold bounces на pull-back`ах у тренді залишаються profitable.

## Дія

- Видалила ADX gate з `trader._decide_one` — LLM signals не обмежуються regime-фільтром
- Зберегла `bb_regime_filtered` як окрему opt-in стратегію (хто хоче менший MaxDD ціною PnL)
- У `smart_picker` regime check лишається але тільки як per-voter filter (BB voter / Momentum voter), не блокує LLM або RL voter
- `regime_ok_for_mean_reversion(adx) = adx < 30` залишено в consensus.py для випадків де треба
