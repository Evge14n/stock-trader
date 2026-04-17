from __future__ import annotations

import sqlite3
from datetime import datetime

import pandas as pd

from agents.python import paper_broker
from agents.python.data_collector import fetch_candles
from agents.python.indicators import (
    _to_df,
    calc_bollinger,
    calc_macd,
    calc_rsi,
)


class BacktestResult:
    def __init__(self):
        self.trades: list[dict] = []
        self.equity_curve: list[dict] = []
        self.initial_capital: float = 0.0
        self.final_capital: float = 0.0

    @property
    def total_pnl(self) -> float:
        return self.final_capital - self.initial_capital

    @property
    def total_pnl_pct(self) -> float:
        if not self.initial_capital:
            return 0.0
        return (self.final_capital - self.initial_capital) / self.initial_capital * 100

    @property
    def win_rate(self) -> float:
        if not self.trades:
            return 0.0
        wins = [t for t in self.trades if t["pnl"] > 0]
        return len(wins) / len(self.trades)

    @property
    def max_drawdown(self) -> float:
        if not self.equity_curve:
            return 0.0
        values = [p["equity"] for p in self.equity_curve]
        peak = values[0]
        max_dd = 0.0
        for v in values:
            peak = max(peak, v)
            dd = (peak - v) / peak if peak else 0.0
            max_dd = max(max_dd, dd)
        return max_dd * 100

    @property
    def sharpe_ratio(self) -> float:
        if len(self.equity_curve) < 2:
            return 0.0
        values = [p["equity"] for p in self.equity_curve]
        returns = [(values[i] - values[i - 1]) / values[i - 1] for i in range(1, len(values))]
        if not returns:
            return 0.0
        mean_r = sum(returns) / len(returns)
        std_r = (sum((r - mean_r) ** 2 for r in returns) / len(returns)) ** 0.5
        if std_r == 0:
            return 0.0
        return (mean_r / std_r) * (252 ** 0.5)

    def summary(self) -> dict:
        return {
            "initial_capital": round(self.initial_capital, 2),
            "final_capital": round(self.final_capital, 2),
            "total_pnl": round(self.total_pnl, 2),
            "total_pnl_pct": round(self.total_pnl_pct, 2),
            "total_trades": len(self.trades),
            "wins": len([t for t in self.trades if t["pnl"] > 0]),
            "losses": len([t for t in self.trades if t["pnl"] < 0]),
            "win_rate": round(self.win_rate * 100, 2),
            "max_drawdown": round(self.max_drawdown, 2),
            "sharpe_ratio": round(self.sharpe_ratio, 2),
        }


def bb_mean_reversion_signal(df: pd.DataFrame, i: int) -> str:
    if i < 30:
        return "hold"

    window = df.iloc[:i + 1]
    closes = window["close"]

    rsi = calc_rsi(closes)
    bb = calc_bollinger(closes)
    macd = calc_macd(closes)

    bull_score = 0
    if rsi < 35:
        bull_score += 2
    elif rsi < 45:
        bull_score += 1
    if bb["bb_position"] < 0.25:
        bull_score += 2
    elif bb["bb_position"] < 0.4:
        bull_score += 1
    if macd["histogram"] > 0:
        bull_score += 1

    if bull_score >= 3:
        return "buy"
    if rsi > 70 and bb["bb_position"] > 0.85:
        return "sell"
    return "hold"


def run_backtest(
    symbols: list[str],
    initial_capital: float = 100_000.0,
    period: str = "6mo",
    risk_per_trade: float = 0.02,
    max_positions: int = 5,
    stop_loss_pct: float = 0.04,
    take_profit_pct: float = 0.08,
) -> BacktestResult:
    result = BacktestResult()
    result.initial_capital = initial_capital

    data_by_symbol = {}
    for sym in symbols:
        candles = fetch_candles(sym, period=period)
        if candles:
            data_by_symbol[sym] = _to_df(candles)

    if not data_by_symbol:
        return result

    all_ts_set = set()
    for df in data_by_symbol.values():
        for i in range(len(df)):
            all_ts_set.add(int(df.iloc[i]["timestamp"]))
    all_timestamps = sorted(all_ts_set)

    cash = initial_capital
    positions: dict[str, dict] = {}

    for ts in all_timestamps:
        daily_prices = {}
        for sym, df in data_by_symbol.items():
            row = df[df["timestamp"] == ts]
            if not row.empty:
                daily_prices[sym] = {
                    "price": float(row.iloc[0]["close"]),
                    "high": float(row.iloc[0]["high"]),
                    "low": float(row.iloc[0]["low"]),
                    "idx": df[df["timestamp"] == ts].index[0],
                }

        closed_today = []
        for sym, pos in list(positions.items()):
            px = daily_prices.get(sym)
            if not px:
                continue

            high = px["high"]
            low = px["low"]
            px["price"]

            exit_reason = None
            exit_price = None

            if low <= pos["stop_loss"]:
                exit_reason = "stop_loss"
                exit_price = pos["stop_loss"]
            elif high >= pos["take_profit"]:
                exit_reason = "take_profit"
                exit_price = pos["take_profit"]

            if exit_reason:
                pnl = (exit_price - pos["entry"]) * pos["qty"]
                cash += pos["qty"] * exit_price
                result.trades.append({
                    "symbol": sym,
                    "entry": pos["entry"],
                    "exit": exit_price,
                    "qty": pos["qty"],
                    "pnl": round(pnl, 2),
                    "pnl_pct": round((exit_price - pos["entry"]) / pos["entry"] * 100, 2),
                    "opened_at": pos["opened_at"],
                    "closed_at": datetime.fromtimestamp(ts).isoformat(),
                    "reason": exit_reason,
                })
                closed_today.append(sym)

        for sym in closed_today:
            del positions[sym]

        if len(positions) < max_positions:
            for sym, px in daily_prices.items():
                if sym in positions:
                    continue

                df = data_by_symbol[sym]
                idx = px["idx"]
                if idx < 30:
                    continue

                df.iloc[:idx + 1]
                signal = bb_mean_reversion_signal(df, idx)

                if signal == "buy":
                    risk_amount = cash * risk_per_trade
                    risk_per_share = px["price"] * stop_loss_pct
                    if risk_per_share <= 0:
                        continue

                    max_position_cost = cash * 0.2
                    qty_by_risk = int(risk_amount / risk_per_share)
                    qty_by_cap = int(max_position_cost / px["price"])
                    qty = min(qty_by_risk, qty_by_cap)
                    cost = qty * px["price"]

                    if qty > 0 and cost <= cash:
                        positions[sym] = {
                            "entry": px["price"],
                            "qty": qty,
                            "stop_loss": round(px["price"] * (1 - stop_loss_pct), 2),
                            "take_profit": round(px["price"] * (1 + take_profit_pct), 2),
                            "opened_at": datetime.fromtimestamp(ts).isoformat(),
                        }
                        cash -= cost

                        if len(positions) >= max_positions:
                            break

        positions_value = sum(p["qty"] * daily_prices.get(sym, {"price": p["entry"]})["price"]
                              for sym, p in positions.items())
        equity = cash + positions_value
        result.equity_curve.append({
            "timestamp": datetime.fromtimestamp(ts).isoformat(),
            "cash": round(cash, 2),
            "positions_value": round(positions_value, 2),
            "equity": round(equity, 2),
            "open_positions": len(positions),
        })

    final_prices = {}
    for sym, df in data_by_symbol.items():
        final_prices[sym] = float(df.iloc[-1]["close"])

    for sym, pos in positions.items():
        exit_price = final_prices.get(sym, pos["entry"])
        pnl = (exit_price - pos["entry"]) * pos["qty"]
        cash += pos["qty"] * exit_price
        result.trades.append({
            "symbol": sym,
            "entry": pos["entry"],
            "exit": exit_price,
            "qty": pos["qty"],
            "pnl": round(pnl, 2),
            "pnl_pct": round((exit_price - pos["entry"]) / pos["entry"] * 100, 2),
            "opened_at": pos["opened_at"],
            "closed_at": result.equity_curve[-1]["timestamp"] if result.equity_curve else "",
            "reason": "end_of_period",
        })

    result.final_capital = cash
    return result


def save_to_broker(result: BacktestResult) -> None:
    paper_broker.reset_account()
    db = paper_broker._db_path()
    db.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(db) as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS account (id INTEGER PRIMARY KEY CHECK (id = 1), cash REAL NOT NULL, initial_deposit REAL NOT NULL, created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS positions (symbol TEXT PRIMARY KEY, qty INTEGER NOT NULL, avg_entry REAL NOT NULL, stop_loss REAL, take_profit REAL, opened_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS trades (id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT NOT NULL, side TEXT NOT NULL, qty INTEGER NOT NULL, entry_price REAL NOT NULL, exit_price REAL, pnl REAL, pnl_pct REAL, opened_at TEXT NOT NULL, closed_at TEXT, close_reason TEXT);
            CREATE TABLE IF NOT EXISTS equity_curve (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT NOT NULL, cash REAL NOT NULL, positions_value REAL NOT NULL, equity REAL NOT NULL, unrealized_pl REAL NOT NULL);
        """)

        conn.execute(
            "INSERT OR REPLACE INTO account (id, cash, initial_deposit, created_at) VALUES (1, ?, ?, ?)",
            (result.final_capital, result.initial_capital, datetime.now().isoformat()),
        )

        for t in result.trades:
            conn.execute(
                "INSERT INTO trades (symbol, side, qty, entry_price, exit_price, pnl, pnl_pct, opened_at, closed_at, close_reason) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    t["symbol"], "long", t["qty"], t["entry"], t["exit"],
                    t["pnl"], t["pnl_pct"] / 100 if t["pnl_pct"] else 0,
                    t["opened_at"], t["closed_at"], t["reason"],
                ),
            )

        for p in result.equity_curve:
            conn.execute(
                "INSERT INTO equity_curve (timestamp, cash, positions_value, equity, unrealized_pl) VALUES (?,?,?,?,?)",
                (p["timestamp"], p["cash"], p["positions_value"], p["equity"], 0.0),
            )

        conn.commit()
