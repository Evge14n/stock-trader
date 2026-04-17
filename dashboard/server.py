from __future__ import annotations

import asyncio
import sys
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import Depends, FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from agents.python import paper_broker
from config.settings import settings
from dashboard.auth import verify_auth


class PipelineRunner:
    def __init__(self):
        self.running = False
        self.last_result: dict | None = None
        self.activity_log: list[dict] = []
        self.auto_mode = False
        self.interval_sec = 3600

    def log(self, event: str, data: dict | None = None):
        entry = {
            "timestamp": datetime.now().isoformat(),
            "event": event,
            "data": data or {},
        }
        self.activity_log.insert(0, entry)
        self.activity_log = self.activity_log[:100]

    async def run_once(self, dry_run: bool = False):
        if self.running:
            return {"error": "already running"}

        self.running = True
        self.log("cycle_started", {"dry_run": dry_run})

        try:
            import uuid

            from core.orchestrator import build_graph

            cycle_id = str(uuid.uuid4())[:8]
            initial_state = {
                "cycle_id": cycle_id,
                "symbols": settings.symbols,
                "market_data": {},
                "indicators": {},
                "news": {},
                "analyses": {},
                "signals": [],
                "risk_checks": [],
                "approved_trades": [],
                "execution_results": [],
                "errors": [],
                "dry_run": dry_run,
                "started_at": datetime.now().isoformat(),
                "completed_at": "",
            }

            graph = build_graph()
            app = graph.compile()

            final_state = None
            async for event in app.astream(initial_state):
                for node_name, node_state in event.items():
                    self.log("node_completed", {"node": node_name})
                    final_state = node_state

            self.last_result = final_state
            self.log(
                "cycle_completed",
                {
                    "cycle_id": cycle_id,
                    "signals": len(final_state.get("signals", [])),
                    "executed": len(final_state.get("execution_results", [])),
                },
            )
            return final_state
        except Exception as e:
            self.log("cycle_error", {"error": str(e)})
            return {"error": str(e)}
        finally:
            self.running = False

    async def auto_loop(self):
        while self.auto_mode:
            await self.run_once(dry_run=False)
            await asyncio.sleep(self.interval_sec)


runner = PipelineRunner()


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(
    title="Stock Trader Dashboard",
    lifespan=lifespan,
    dependencies=[Depends(verify_auth)],
)

static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/", response_class=HTMLResponse)
async def index():
    html_path = Path(__file__).parent / "static" / "index.html"
    return HTMLResponse(html_path.read_text(encoding="utf-8"))


def _yf_price(sym: str) -> float | None:
    import yfinance as yf

    try:
        hist = yf.Ticker(sym).history(period="1d", interval="1m")
        if not hist.empty:
            return float(hist["Close"].iloc[-1])
        daily = yf.Ticker(sym).history(period="5d")
        if not daily.empty:
            return float(daily["Close"].iloc[-1])
    except Exception:
        return None
    return None


@app.get("/api/portfolio")
async def portfolio():
    positions = paper_broker.list_positions()
    symbols = [p["symbol"] for p in positions]
    prices = {}

    if symbols:
        results = await asyncio.gather(*[asyncio.to_thread(_yf_price, sym) for sym in symbols])
        for sym, price in zip(symbols, results, strict=False):
            if price is not None:
                prices[sym] = price

    positions_live = paper_broker.list_positions(prices)
    account = paper_broker.get_account()
    positions_value = sum(p["qty"] * p["current_price"] for p in positions_live)
    equity = account["cash"] + positions_value

    total_pl = equity - account["initial_deposit"]
    total_pl_pct = total_pl / account["initial_deposit"] if account["initial_deposit"] else 0.0

    return {
        "cash": account["cash"],
        "initial_deposit": account["initial_deposit"],
        "equity": equity,
        "positions_value": positions_value,
        "total_pl": round(total_pl, 2),
        "total_pl_pct": round(total_pl_pct * 100, 3),
        "unrealized_pl": round(sum(p["unrealized_pl"] for p in positions_live), 2),
        "position_count": len(positions_live),
        "positions": positions_live,
    }


@app.get("/api/equity_history")
async def equity_history(limit: int = 500):
    return paper_broker.get_equity_history(limit)


@app.get("/api/stats")
async def stats():
    return paper_broker.get_trade_stats()


@app.get("/api/trades")
async def trades(limit: int = 500):
    import sqlite3

    with sqlite3.connect(paper_broker._db_path()) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM trades ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


@app.get("/api/trades/csv")
async def trades_csv():
    import csv
    import io as strio
    import sqlite3

    from fastapi.responses import PlainTextResponse

    with sqlite3.connect(paper_broker._db_path()) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM trades ORDER BY id ASC").fetchall()

    buf = strio.StringIO()
    if rows:
        writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        for r in rows:
            writer.writerow(dict(r))

    return PlainTextResponse(
        buf.getvalue(),
        headers={"Content-Disposition": "attachment; filename=trades.csv"},
        media_type="text/csv",
    )


@app.get("/api/analytics")
async def analytics():
    import sqlite3

    with sqlite3.connect(paper_broker._db_path()) as conn:
        conn.row_factory = sqlite3.Row
        trades = conn.execute("SELECT * FROM trades WHERE closed_at IS NOT NULL ORDER BY id ASC").fetchall()
        equity = conn.execute("SELECT equity, timestamp FROM equity_curve ORDER BY id ASC").fetchall()

    by_symbol: dict[str, dict] = {}
    pnl_buckets: dict[str, int] = {
        "<-500": 0,
        "-500_to_-200": 0,
        "-200_to_0": 0,
        "0_to_200": 0,
        "200_to_500": 0,
        ">500": 0,
    }

    for t in trades:
        sym = t["symbol"]
        pnl = t["pnl"] or 0
        if sym not in by_symbol:
            by_symbol[sym] = {"trades": 0, "wins": 0, "losses": 0, "pnl": 0.0}
        by_symbol[sym]["trades"] += 1
        by_symbol[sym]["pnl"] += pnl
        if pnl > 0:
            by_symbol[sym]["wins"] += 1
        elif pnl < 0:
            by_symbol[sym]["losses"] += 1

        if pnl < -500:
            pnl_buckets["<-500"] += 1
        elif pnl < -200:
            pnl_buckets["-500_to_-200"] += 1
        elif pnl < 0:
            pnl_buckets["-200_to_0"] += 1
        elif pnl < 200:
            pnl_buckets["0_to_200"] += 1
        elif pnl < 500:
            pnl_buckets["200_to_500"] += 1
        else:
            pnl_buckets[">500"] += 1

    drawdown = []
    peak = 0.0
    for row in equity:
        v = row["equity"]
        peak = max(peak, v)
        dd_pct = (v - peak) / peak * 100 if peak else 0.0
        drawdown.append({"timestamp": row["timestamp"], "drawdown": round(dd_pct, 2)})

    return {
        "by_symbol": {k: {**v, "pnl": round(v["pnl"], 2)} for k, v in by_symbol.items()},
        "pnl_distribution": pnl_buckets,
        "drawdown": drawdown,
    }


@app.get("/api/regime")
async def regime():
    from agents.python.data_collector import fetch_candles
    from agents.python.regime_detector import detect_portfolio_regime

    def _load():
        data = {}
        for sym in settings.symbols[:5]:
            candles = fetch_candles(sym, period="3mo")
            if candles:
                data[sym] = candles
        return data

    market_data = await asyncio.to_thread(_load)
    return detect_portfolio_regime(market_data)


@app.get("/api/monte_carlo")
async def monte_carlo(days: int = 252, simulations: int = 1000):
    from agents.python.monte_carlo import run_from_backtest_result

    equity = paper_broker.get_equity_history(limit=10000)
    if len(equity) < 2:
        return {"error": "not enough equity history", "min_points": 2, "current_points": len(equity)}

    account = paper_broker.get_account()
    initial = account["equity"] if account["equity"] > 0 else 100_000.0

    report = await asyncio.to_thread(run_from_backtest_result, equity, initial, days, simulations)
    summary = report.summary()

    final_sorted = sorted(report.final_equities) if report.final_equities else []
    if final_sorted:
        hist_buckets = 20
        min_v = min(final_sorted)
        max_v = max(final_sorted)
        bucket_size = (max_v - min_v) / hist_buckets if max_v > min_v else 1
        histogram = []
        for i in range(hist_buckets):
            lo = min_v + i * bucket_size
            hi = min_v + (i + 1) * bucket_size
            count = sum(1 for v in final_sorted if lo <= v < hi)
            histogram.append({"range_start": round(lo, 0), "range_end": round(hi, 0), "count": count})
    else:
        histogram = []

    return {**summary, "histogram": histogram, "initial_capital": initial}


@app.get("/api/explain")
async def explain():
    from agents.python.explainer import explain_all
    from core.orchestrator import _dict_to_state

    if not runner.last_result:
        return {"error": "no pipeline data", "hint": "run a cycle first"}

    ps = _dict_to_state(runner.last_result)
    return {"explanations": explain_all(ps)}


@app.post("/api/export_dataset")
async def export_dataset():
    from agents.python.fine_tuning import export_training_dataset, generate_kaggle_notebook

    dataset_path = await asyncio.to_thread(export_training_dataset)
    notebook_path = await asyncio.to_thread(generate_kaggle_notebook)

    return {
        "dataset": str(dataset_path),
        "notebook": str(notebook_path),
        "instructions": [
            "1. Upload fine_tune_dataset.jsonl as Kaggle dataset",
            "2. Open stock_trader_finetune.ipynb in Kaggle (free T4 GPU)",
            "3. Run all cells (30-60 min)",
            "4. Download resulting GGUF file",
            "5. ollama create gemma-stock-trader -f Modelfile",
            "6. Set OLLAMA_MODEL=gemma-stock-trader in .env",
        ],
    }


@app.get("/api/benchmark")
async def benchmark():
    from agents.python.benchmark import get_comparison

    return await asyncio.to_thread(get_comparison)


@app.get("/api/sector_heatmap")
async def sector_heatmap():
    from agents.python.dashboard_data import sector_heatmap as sh

    return await asyncio.to_thread(sh)


@app.get("/api/allocation")
async def allocation():
    from agents.python.dashboard_data import portfolio_allocation

    return await asyncio.to_thread(portfolio_allocation)


@app.get("/api/news_feed")
async def news_feed():
    from agents.python.dashboard_data import fetch_live_news

    return await asyncio.to_thread(fetch_live_news, 3)


@app.get("/api/macro")
async def macro():
    from agents.python.macro import get_macro_summary

    return await asyncio.to_thread(get_macro_summary)


@app.post("/api/tune")
async def run_auto_tuning():
    from agents.python.self_tuner import run_tuning_cycle

    return await asyncio.to_thread(run_tuning_cycle, True)


@app.get("/api/tune/history")
async def tuning_history(limit: int = 10):
    from agents.python.self_tuner import get_tuning_history

    return await asyncio.to_thread(get_tuning_history, limit)


@app.post("/api/strategy/auto_switch")
async def strategy_auto_switch():
    from agents.python.regime_switcher import auto_switch_strategy

    return await asyncio.to_thread(auto_switch_strategy)


@app.get("/api/strategy/active")
async def active_strategy():
    from agents.python.regime_switcher import load_active_strategy

    return await asyncio.to_thread(load_active_strategy)


@app.post("/api/strategy/override")
async def override_strategy(name: str):
    from agents.python.regime_switcher import override_strategy as _override

    return await asyncio.to_thread(_override, name)


@app.post("/api/evolve")
async def evolve():
    from agents.python.genetic_evolver import evolve_generation

    return await evolve_generation()


@app.get("/api/evolved_strategies")
async def evolved_strategies():
    from agents.python.genetic_evolver import load_population

    pop = await asyncio.to_thread(load_population)
    return [
        {"name": p.name, "fitness": p.fitness, "generation": p.generation, "backtest": p.backtest} for p in pop[:20]
    ]


@app.post("/api/forecaster/train/{symbol}")
async def forecaster_train(symbol: str):
    from agents.python.forecaster import train_forecaster

    return await asyncio.to_thread(train_forecaster, symbol)


@app.get("/api/forecaster/predict/{symbol}")
async def forecaster_predict(symbol: str):
    from agents.python.forecaster import predict_next_return

    return await asyncio.to_thread(predict_next_return, symbol)


@app.post("/api/forecaster/train_all")
async def forecaster_train_all():
    from agents.python.forecaster import train_all_watchlist

    return await asyncio.to_thread(train_all_watchlist)


@app.get("/api/pair_trading")
async def pair_trading():
    from agents.python.pair_trading import get_best_pair_opportunities

    return await asyncio.to_thread(get_best_pair_opportunities, settings.symbols, "6mo", 10)


@app.get("/api/volume_profile/{symbol}")
async def volume_profile(symbol: str):
    from agents.python.data_collector import fetch_candles
    from agents.python.volume_profile import analyze_symbol

    candles = await asyncio.to_thread(fetch_candles, symbol, "3mo")
    if not candles:
        return {"error": "no candles"}
    return await asyncio.to_thread(analyze_symbol, symbol, candles)


@app.get("/api/weights")
async def ensemble_weights():
    from agents.python.ensemble_weights import load_weights

    return await asyncio.to_thread(load_weights)


@app.post("/api/weights/recompute")
async def recompute_weights():
    from agents.python.ensemble_weights import recompute_weights as _recompute

    return await asyncio.to_thread(_recompute, [])


@app.post("/api/pdf_report")
async def generate_pdf_report():
    from fastapi.responses import FileResponse

    from agents.python.pdf_report import generate_report

    path = await asyncio.to_thread(generate_report)
    return FileResponse(str(path), media_type="application/pdf", filename=path.name)


@app.post("/api/generate_strategy")
async def generate_strategy():
    from agents.python.strategy_generator import generate_and_backtest, save_strategy

    result = await generate_and_backtest()
    if result.valid and result.backtest_summary.get("total_trades", 0) > 0:
        save_strategy(result)
    return {
        "valid": result.valid,
        "name": result.name,
        "code": result.code,
        "error": result.error,
        "backtest": result.backtest_summary,
    }


@app.get("/api/generated_strategies")
async def list_generated():
    from agents.python.strategy_generator import load_saved_strategies

    return await asyncio.to_thread(load_saved_strategies)


@app.post("/api/daily_report")
async def trigger_daily_report():
    from agents.python.daily_report import send_daily_report

    ok = await send_daily_report()
    return {"sent": ok}


@app.get("/api/voting")
async def voting():
    if not runner.last_result:
        return {"symbols": []}

    analyses = runner.last_result.get("analyses", {})
    signals = runner.last_result.get("signals", [])
    approved = runner.last_result.get("approved_trades", [])

    signals_by_symbol: dict[str, dict] = {}
    for s in signals:
        sym = s.get("symbol") if isinstance(s, dict) else getattr(s, "symbol", None)
        if sym:
            signals_by_symbol[sym] = s if isinstance(s, dict) else s.__dict__

    approved_by_symbol = {(a.get("symbol") if isinstance(a, dict) else getattr(a, "symbol", None)) for a in approved}

    out = []
    for sym, entries in analyses.items():
        picker_entries = [
            e
            for e in entries
            if (e.get("agent") if isinstance(e, dict) else getattr(e, "agent", None)) == "smart_picker"
        ]
        if not picker_entries:
            continue
        latest = picker_entries[-1]
        reasoning = latest.get("reasoning", "") if isinstance(latest, dict) else getattr(latest, "reasoning", "")
        votes = []
        for part in reasoning.split(";"):
            part = part.strip()
            if not part or ":" not in part:
                continue
            try:
                source, rest = part.split(":", 1)
                action_str, conf_str = rest.split("@")
                votes.append(
                    {
                        "source": source.strip(),
                        "action": action_str.strip(),
                        "confidence": float(conf_str.strip()),
                    }
                )
            except (ValueError, IndexError):
                continue

        signal = signals_by_symbol.get(sym)
        out.append(
            {
                "symbol": sym,
                "votes": votes,
                "signal_emitted": signal is not None,
                "signal_action": signal.get("action") if signal else None,
                "signal_confidence": signal.get("confidence") if signal else None,
                "approved": sym in approved_by_symbol,
            }
        )

    out.sort(key=lambda x: (-int(x["signal_emitted"]), -len(x["votes"])))
    return {"symbols": out}


@app.get("/api/rl")
async def rl_status():
    import json

    rl_dir = settings.data_dir / "rl"
    model_path = rl_dir / "ppo_latest.zip"
    meta_path = rl_dir / "ppo_latest.json"

    payload: dict = {
        "enabled": settings.use_rl_decision,
        "model_available": model_path.exists(),
        "model_path": str(model_path) if model_path.exists() else None,
        "model_size_mb": round(model_path.stat().st_size / (1024 * 1024), 2) if model_path.exists() else 0,
        "meta": None,
        "deps_installed": False,
    }

    try:
        import stable_baselines3  # noqa: F401

        payload["deps_installed"] = True
    except ImportError:
        pass

    if meta_path.exists():
        try:
            payload["meta"] = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            payload["meta"] = None

    return payload


@app.get("/api/circuit_breaker")
async def circuit_breaker_status():
    from agents.python.circuit_breaker import check_drawdown, check_loss_streak, is_trading_hours

    return {
        "drawdown": check_drawdown(),
        "trading_hours": is_trading_hours(),
        "loss_streak": check_loss_streak(settings.max_consecutive_losses, settings.loss_cooldown_hours),
    }


@app.get("/api/orders")
async def orders(limit: int = 50):
    import sqlite3

    with sqlite3.connect(paper_broker._db_path()) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM orders ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


@app.get("/api/activity")
async def activity():
    return runner.activity_log


@app.get("/api/status")
async def status():
    return {
        "running": runner.running,
        "auto_mode": runner.auto_mode,
        "interval_sec": runner.interval_sec,
        "watchlist": settings.symbols,
        "model": settings.ollama_model,
    }


_background_tasks: set[asyncio.Task] = set()


def _spawn(coro) -> asyncio.Task:
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return task


@app.post("/api/run")
async def run(dry_run: bool = False):
    if runner.running:
        return JSONResponse({"error": "already running"}, status_code=409)
    _spawn(runner.run_once(dry_run=dry_run))
    return {"started": True}


@app.post("/api/auto/start")
async def auto_start(interval: int = 3600):
    if runner.auto_mode:
        return {"status": "already_running"}
    runner.auto_mode = True
    runner.interval_sec = interval
    _spawn(runner.auto_loop())
    return {"status": "started", "interval": interval}


@app.post("/api/auto/stop")
async def auto_stop():
    runner.auto_mode = False
    return {"status": "stopped"}


@app.post("/api/reset")
async def reset():
    paper_broker.reset_account()
    runner.log("account_reset", {})
    return {"status": "reset"}


@app.get("/api/analyses")
async def latest_analyses():
    if not runner.last_result:
        return {"analyses": {}, "signals": [], "executed": []}
    return {
        "analyses": runner.last_result.get("analyses", {}),
        "signals": runner.last_result.get("signals", []),
        "executed": runner.last_result.get("execution_results", []),
        "cycle_id": runner.last_result.get("cycle_id", ""),
        "completed_at": runner.last_result.get("completed_at", ""),
    }


@app.get("/api/market")
async def market_snapshot():
    import yfinance as yf

    def _yf_quote(sym):
        try:
            t = yf.Ticker(sym)
            hist = t.history(period="5d", interval="1d")
            if hist.empty:
                return {"error": "no data"}
            price = float(hist["Close"].iloc[-1])
            prev = float(hist["Close"].iloc[-2]) if len(hist) > 1 else price
            change = ((price - prev) / prev * 100) if prev else 0.0
            return {"price": round(price, 2), "prev_close": round(prev, 2), "change_pct": round(change, 2)}
        except Exception as e:
            return {"error": str(e)[:60]}

    quotes = {}
    results = await asyncio.gather(*[asyncio.to_thread(_yf_quote, sym) for sym in settings.symbols])
    for sym, q in zip(settings.symbols, results, strict=False):
        quotes[sym] = q
    return quotes


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
