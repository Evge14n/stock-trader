from __future__ import annotations

import asyncio
import sys
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from agents.python import paper_broker
from agents.python.data_collector import fetch_quote
from config.settings import settings


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


app = FastAPI(title="Stock Trader Dashboard", lifespan=lifespan)

static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/", response_class=HTMLResponse)
async def index():
    html_path = Path(__file__).parent / "static" / "index.html"
    return HTMLResponse(html_path.read_text(encoding="utf-8"))


@app.get("/api/portfolio")
async def portfolio():
    positions = paper_broker.list_positions()
    symbols = [p["symbol"] for p in positions]
    prices = {}

    for sym in symbols:
        try:
            q = await asyncio.to_thread(fetch_quote, sym)
            prices[sym] = q["price"]
        except Exception:
            pass

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
