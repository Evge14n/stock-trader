from __future__ import annotations

import math
from datetime import datetime

import yfinance as yf

from agents.python import paper_broker


def fetch_benchmark_curve(start_timestamp: str, benchmark: str = "SPY") -> list[dict]:
    try:
        start_dt = datetime.fromisoformat(start_timestamp.replace("Z", "+00:00"))
    except Exception:
        start_dt = datetime.now()

    days_since = (datetime.now() - start_dt.replace(tzinfo=None)).days
    period = (
        "1mo"
        if days_since < 30
        else "3mo"
        if days_since < 90
        else "6mo"
        if days_since < 180
        else "1y"
        if days_since < 365
        else "2y"
    )

    try:
        ticker = yf.Ticker(benchmark)
        hist = ticker.history(period=period, interval="1d")
        if hist.empty:
            return []
    except Exception:
        return []

    rows = []
    for idx, row in hist.iterrows():
        rows.append(
            {
                "timestamp": idx.isoformat() if hasattr(idx, "isoformat") else str(idx),
                "close": float(row["Close"]),
                "volume": int(row["Volume"]) if not math.isnan(row["Volume"]) else 0,
            }
        )
    return rows


def compare_to_benchmark(equity_history: list[dict], benchmark: str = "SPY") -> dict:
    if not equity_history:
        return {"error": "no equity history"}

    first_ts = equity_history[0]["timestamp"]
    initial_equity = equity_history[0]["equity"]
    current_equity = equity_history[-1]["equity"]

    bench_curve = fetch_benchmark_curve(first_ts, benchmark)
    if not bench_curve:
        return {"error": "could not fetch benchmark"}

    bench_start = bench_curve[0]["close"]
    bench_end = bench_curve[-1]["close"]
    bench_pct = (bench_end - bench_start) / bench_start * 100 if bench_start else 0

    portfolio_pct = (current_equity - initial_equity) / initial_equity * 100 if initial_equity else 0
    alpha_pct = portfolio_pct - bench_pct

    portfolio_returns = []
    for i in range(1, len(equity_history)):
        prev = equity_history[i - 1]["equity"]
        curr = equity_history[i]["equity"]
        if prev:
            portfolio_returns.append((curr - prev) / prev)

    bench_returns = []
    for i in range(1, len(bench_curve)):
        prev = bench_curve[i - 1]["close"]
        curr = bench_curve[i]["close"]
        if prev:
            bench_returns.append((curr - prev) / prev)

    beta = 0.0
    if len(portfolio_returns) >= 5 and len(bench_returns) >= 5:
        min_len = min(len(portfolio_returns), len(bench_returns))
        p = portfolio_returns[-min_len:]
        b = bench_returns[-min_len:]

        mean_p = sum(p) / len(p)
        mean_b = sum(b) / len(b)

        cov = sum((p[i] - mean_p) * (b[i] - mean_b) for i in range(min_len)) / min_len
        var_b = sum((b[i] - mean_b) ** 2 for i in range(min_len)) / min_len

        beta = cov / var_b if var_b else 0.0

    normalized_bench = []
    if bench_start:
        for point in bench_curve:
            normalized = (point["close"] / bench_start) * initial_equity
            normalized_bench.append(
                {
                    "timestamp": point["timestamp"],
                    "equity": round(normalized, 2),
                }
            )

    return {
        "benchmark": benchmark,
        "portfolio_return_pct": round(portfolio_pct, 3),
        "benchmark_return_pct": round(bench_pct, 3),
        "alpha_pct": round(alpha_pct, 3),
        "beta": round(beta, 3),
        "beating_market": alpha_pct > 0,
        "portfolio_start": round(initial_equity, 2),
        "portfolio_end": round(current_equity, 2),
        "benchmark_normalized_curve": normalized_bench,
    }


def get_comparison() -> dict:
    equity = paper_broker.get_equity_history(limit=10000)
    if not equity:
        account = paper_broker.get_account()
        equity = [
            {
                "timestamp": account.get("created_at", datetime.now().isoformat()),
                "equity": account["initial_deposit"],
            }
        ]
    return compare_to_benchmark(equity)
