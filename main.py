from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from agents.python import portfolio_tracker
from config.settings import settings
from core import llm_client
from core.orchestrator import build_graph

console = Console()


def print_banner():
    console.print(
        Panel.fit(
            "[bold cyan]Stock Trader[/] — Multi-Agent AI Trading System\n"
            f"Model: {settings.ollama_model} | Symbols: {len(settings.symbols)} | Paper Trading",
            border_style="cyan",
        )
    )


async def check_dependencies(dry_run: bool = False) -> bool:
    checks = []

    llm_ok = await llm_client.health_check()
    checks.append(("Ollama + Gemma 4", llm_ok, True))

    api_ok = bool(settings.finnhub_api_key)
    checks.append(("Finnhub API", api_ok, True))

    from agents.python import paper_broker

    try:
        acc = paper_broker.get_account()
        broker_ok = acc["equity"] > 0
    except Exception:
        broker_ok = False
    checks.append(("Paper Broker (local)", broker_ok, True))

    try:
        from agents.python.data_collector import fetch_candles

        sample = fetch_candles("AAPL", period="5d")
        yf_ok = len(sample) >= 1
    except Exception:
        yf_ok = False
    checks.append(("Yahoo Finance", yf_ok, True))

    try:
        from core import smart_picker

        voters_ok = all(
            callable(getattr(smart_picker, name, None))
            for name in ("_llm_vote", "_bb_vote", "_momentum_vote", "_rl_vote", "_forecaster_vote", "_rs_vote")
        )
    except Exception:
        voters_ok = False
    checks.append(("Smart Picker (6 voters)", voters_ok, True))

    try:
        from agents.python.voter_stats import get_all_stats

        get_all_stats()
        voter_db_ok = True
    except Exception:
        voter_db_ok = False
    checks.append(("Voter Stats DB", voter_db_ok, True))

    try:
        from agents.python.circuit_breaker import check_drawdown

        check_drawdown()
        cb_ok = True
    except Exception:
        cb_ok = False
    checks.append(("Circuit Breaker", cb_ok, True))

    try:
        from agents.python.market_regime import detect

        regime = detect(settings.symbols[:3])
        regime_ok = regime.label != ""
    except Exception:
        regime_ok = False
    checks.append(("Market Regime", regime_ok, False))

    tg_ok = bool(settings.telegram_bot_token and settings.telegram_chat_id)
    checks.append(("Telegram (optional)", tg_ok, False))

    table = Table(title="System Check", box=box.SIMPLE)
    table.add_column("Component", style="cyan")
    table.add_column("Status")

    all_ok = True
    for name, ok, required in checks:
        if ok:
            status = "[green]OK[/]"
        elif required:
            status = "[red]MISSING[/]"
            all_ok = False
        else:
            status = "[yellow]OPTIONAL[/]"
        table.add_row(name, status)

    console.print(table)
    return all_ok


async def run_cycle(dry_run: bool = False):
    cycle_id = str(uuid.uuid4())[:8]
    console.print(f"\n[bold yellow]Cycle {cycle_id}[/] started at {datetime.now().strftime('%H:%M:%S')}")

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
            console.print(f"  [dim]> {node_name}[/]")
            final_state = node_state

    if not final_state:
        console.print("[red]Pipeline returned empty state[/]")
        return

    print_results(final_state)


def print_results(state: dict):
    console.print()

    analyses = state.get("analyses", {})
    if analyses:
        table = Table(title="Analyses", box=box.ROUNDED)
        table.add_column("Symbol", style="cyan")
        table.add_column("Agent")
        table.add_column("Signal")
        table.add_column("Confidence")

        for symbol, items in analyses.items():
            for a in items:
                sig = a if isinstance(a, dict) else {"signal": str(a)}
                signal = sig.get("signal", "?")
                color = (
                    "green"
                    if "bull" in signal or "buy" in signal
                    else "red"
                    if "bear" in signal or "sell" in signal
                    else "yellow"
                )
                table.add_row(
                    symbol,
                    sig.get("agent", "?"),
                    f"[{color}]{signal}[/]",
                    f"{sig.get('confidence', 0):.2f}",
                )
        console.print(table)

    signals = state.get("signals", [])
    approved = state.get("approved_trades", [])
    results = state.get("execution_results", [])

    console.print(f"\n  Signals generated: {len(signals)}")
    console.print(f"  Approved by risk: {len(approved)}")
    console.print(f"  Orders executed: {len(results)}")

    if results:
        table = Table(title="Executed Trades", box=box.ROUNDED)
        table.add_column("Symbol", style="cyan")
        table.add_column("Side")
        table.add_column("Qty")
        table.add_column("Status")

        for r in results:
            if isinstance(r, dict):
                side = r.get("side", "?")
                color = "green" if "buy" in str(side).lower() else "red"
                table.add_row(
                    r.get("symbol", "?"),
                    f"[{color}]{side}[/]",
                    str(r.get("qty", "?")),
                    r.get("status", r.get("error", "?")),
                )
        console.print(table)

    errors = state.get("errors", [])
    if errors:
        console.print(f"\n[yellow]Warnings ({len(errors)}):[/]")
        for e in errors[:5]:
            console.print(f"  [dim]{e}[/]")


async def run_loop(interval: int, dry_run: bool = False):
    console.print(f"[bold]Loop mode[/]: cycle every {interval}s (Ctrl+C to stop)")
    while True:
        try:
            await run_cycle(dry_run)
            console.print(f"\n[dim]Next cycle in {interval}s...[/]")
            await asyncio.sleep(interval)
        except KeyboardInterrupt:
            console.print("\n[yellow]Stopped by user[/]")
            break


async def show_status():
    snap = portfolio_tracker.snapshot()
    account = snap.get("account", {})
    positions = snap.get("positions", [])

    console.print(
        Panel.fit(
            f"Equity: ${account.get('equity', 0):,.2f}\n"
            f"Cash: ${account.get('cash', 0):,.2f}\n"
            f"Positions: {len(positions)}\n"
            f"Unrealized P/L: ${snap.get('total_unrealized_pl', 0):,.2f}",
            title="Portfolio",
            border_style="green",
        )
    )

    if positions:
        table = Table(title="Open Positions", box=box.ROUNDED)
        table.add_column("Symbol", style="cyan")
        table.add_column("Qty")
        table.add_column("Entry")
        table.add_column("Current")
        table.add_column("P/L")

        for p in positions:
            pl = p.get("unrealized_pl", 0)
            color = "green" if pl >= 0 else "red"
            table.add_row(
                p["symbol"],
                str(p["qty"]),
                f"${p['avg_entry']:.2f}",
                f"${p['current_price']:.2f}",
                f"[{color}]${pl:+.2f}[/]",
            )
        console.print(table)

    stats = portfolio_tracker.summary()
    console.print(
        f"\n  Total trades: {stats['total_trades']} | Win rate: {stats['win_rate']:.1%} | Total P/L: ${stats['total_pl']:+.2f}"
    )


async def run_backtest_cmd(
    period: str,
    symbols: list[str] | None = None,
    save: bool = False,
    strategy: str = "bb_mean_reversion",
):
    from agents.python.backtest import run_backtest, save_to_broker

    syms = symbols or settings.symbols
    console.print(f"\n[bold]Backtest[/] on {len(syms)} symbols, period={period}, strategy={strategy}")
    console.print(f"Symbols: {', '.join(syms)}")
    console.print("[dim]Running historical simulation...[/]\n")

    result = await asyncio.to_thread(run_backtest, syms, 100_000.0, period, 0.02, 5, 0.04, 0.08, strategy)
    summary = result.summary()

    if save:
        save_to_broker(result)
        console.print("[green]Saved backtest results to paper broker DB[/]\n")

    table = Table(title="Backtest Results", box=box.ROUNDED)
    table.add_column("Metric", style="cyan")
    table.add_column("Value", justify="right")

    for k, v in summary.items():
        if isinstance(v, float):
            if "pct" in k or "rate" in k or "drawdown" in k:
                val = f"{v:+.2f}%"
            elif "capital" in k or "pnl" in k:
                val = f"${v:,.2f}"
            else:
                val = f"{v:.2f}"
        else:
            val = str(v)

        color = ""
        if k == "total_pnl" and v > 0:
            color = "[green]"
        elif k == "total_pnl" and v < 0:
            color = "[red]"

        table.add_row(k.replace("_", " ").title(), f"{color}{val}{'[/]' if color else ''}")

    console.print(table)

    if result.trades:
        recent = result.trades[-10:]
        trade_table = Table(title=f"Last {len(recent)} trades", box=box.SIMPLE)
        trade_table.add_column("Symbol")
        trade_table.add_column("Entry", justify="right")
        trade_table.add_column("Exit", justify="right")
        trade_table.add_column("P/L", justify="right")
        trade_table.add_column("Reason")

        for t in recent:
            color = "green" if t["pnl"] > 0 else "red"
            trade_table.add_row(
                t["symbol"],
                f"${t['entry']:.2f}",
                f"${t['exit']:.2f}",
                f"[{color}]${t['pnl']:+,.2f}[/]",
                t["reason"],
            )
        console.print(trade_table)


def run_dashboard():
    import uvicorn

    console.print("[bold cyan]Dashboard[/] running at [underline]http://localhost:8000[/]")
    console.print("[dim]Press Ctrl+C to stop[/]\n")
    uvicorn.run(
        "dashboard.server:app",
        host="0.0.0.0",
        port=8000,
        log_level="warning",
    )


async def run_walk_forward_cmd(period: str, train_days: int, test_days: int):
    from agents.python.walk_forward import run_walk_forward

    console.print(
        f"\n[bold]Walk-forward[/] on {len(settings.symbols)} symbols, period={period}, train={train_days}d, test={test_days}d"
    )
    console.print("[dim]Running rolling backtests...[/]\n")

    report = await asyncio.to_thread(run_walk_forward, settings.symbols, period, train_days, test_days, test_days)
    summary = report.summary()

    table = Table(title="Walk-Forward Results", box=box.ROUNDED)
    table.add_column("Metric", style="cyan")
    table.add_column("Value", justify="right")
    for k, v in summary.items():
        table.add_row(k.replace("_", " ").title(), str(v))
    console.print(table)

    if report.windows:
        w_table = Table(title=f"Windows ({len(report.windows)})", box=box.SIMPLE)
        w_table.add_column("#")
        w_table.add_column("Test period")
        w_table.add_column("Test P/L $", justify="right")
        w_table.add_column("Test P/L %", justify="right")
        for i, w in enumerate(report.windows, 1):
            pnl = w.test_result.get("total_pnl", 0)
            pct = w.test_result.get("total_pnl_pct", 0)
            color = "green" if pnl > 0 else "red"
            w_table.add_row(
                str(i), f"{w.test_start} .. {w.test_end}", f"[{color}]${pnl:+,.2f}[/]", f"[{color}]{pct:+.2f}%[/]"
            )
        console.print(w_table)


async def run_optimize_cmd(period: str):
    from agents.python.optimizer import run_grid_search

    console.print(f"\n[bold]Grid search optimization[/] period={period}")
    console.print("[dim]Testing parameter combinations...[/]\n")

    report = await asyncio.to_thread(run_grid_search, settings.symbols, period)

    if not report.best:
        console.print("[red]No valid combinations found[/]")
        return

    table = Table(title=f"Top 10 parameter sets (of {report.param_space_size})", box=box.ROUNDED)
    for col in ["SL", "TP", "Risk", "P/L %", "Win %", "Sharpe", "MaxDD %", "Trades", "Score"]:
        table.add_column(col, justify="right")

    for r in report.top_n(10):
        color = "green" if r.total_pnl > 0 else "red"
        table.add_row(
            f"{r.stop_loss_pct:.2f}",
            f"{r.take_profit_pct:.2f}",
            f"{r.risk_per_trade:.2f}",
            f"[{color}]{r.total_pnl_pct:+.2f}[/]",
            f"{r.win_rate:.1f}",
            f"{r.sharpe_ratio:.2f}",
            f"{r.max_drawdown:.2f}",
            str(r.total_trades),
            f"{r.score():.2f}",
        )
    console.print(table)
    console.print(
        f"\n[bold green]Best:[/] SL={report.best.stop_loss_pct:.2f}, "
        f"TP={report.best.take_profit_pct:.2f}, Risk={report.best.risk_per_trade:.2f} "
        f"→ P/L {report.best.total_pnl_pct:+.2f}%, Sharpe {report.best.sharpe_ratio:.2f}"
    )


async def run_correlation_cmd(period: str):
    from agents.python.correlation import compute_correlation_matrix

    console.print(f"\n[bold]Correlation matrix[/] period={period}\n")
    result = await asyncio.to_thread(compute_correlation_matrix, settings.symbols, period)

    symbols = result["symbols"]
    matrix = result["matrix"]

    table = Table(title="Correlation matrix", box=box.SIMPLE)
    table.add_column("", style="cyan")
    for sym in symbols:
        table.add_column(sym)

    for sym1 in symbols:
        row = [sym1]
        for sym2 in symbols:
            val = matrix.get(sym1, {}).get(sym2, 0)
            color = "red" if val > 0.8 else "yellow" if val > 0.5 else "green"
            row.append(f"[{color}]{val:.2f}[/]" if val != 1 else f"[dim]{val:.2f}[/]")
        table.add_row(*row)
    console.print(table)

    if result["highly_correlated"]:
        console.print("\n[yellow]Highly correlated pairs (> 0.8):[/]")
        for a, b, c in result["highly_correlated"]:
            console.print(f"  {a} <-> {b}: {c:.2f}")


async def run_rl_train_cmd(period: str, timesteps: int, symbols: list[str] | None = None):
    try:
        from agents.python.rl.trainer import TrainConfig, train
    except ImportError:
        console.print("[red]RL deps not installed. pip install -r requirements-rl.txt[/]")
        return

    syms = symbols or settings.symbols
    console.print(f"\n[bold]RL train[/] symbols={len(syms)} timesteps={timesteps:,} period={period}")
    cfg = TrainConfig(symbols=syms, period=period, total_timesteps=timesteps)
    path = await asyncio.to_thread(train, cfg)
    console.print(f"[green]Model saved:[/] {path}")


async def run_rl_ab_cmd(period: str, train_ratio: float, timesteps: int, symbols: list[str] | None = None):
    try:
        from agents.python.rl.compare import run_ab
    except ImportError:
        console.print("[red]RL deps not installed. pip install -r requirements-rl.txt[/]")
        return

    syms = symbols or settings.symbols
    console.print(
        f"\n[bold]RL vs BB A/B[/] symbols={len(syms)} period={period} train_ratio={train_ratio} timesteps={timesteps:,}"
    )

    report = await asyncio.to_thread(run_ab, syms, period, train_ratio, timesteps)

    table = Table(title="RL vs BB — out-of-sample comparison", box=box.ROUNDED)
    for col in ["Strategy", "Trades", "Wins", "Win %", "Total PnL $", "Total PnL %", "Final Capital $"]:
        table.add_column(col, justify="right")

    for r in (report.rl, report.bb):
        s = r.summary()
        color = "green" if s["total_pnl"] >= 0 else "red"
        table.add_row(
            s["name"],
            str(s["trades"]),
            str(s["wins"]),
            f"{s['win_rate']:.1f}",
            f"[{color}]${s['total_pnl']:+,.2f}[/]",
            f"[{color}]{s['total_pnl_pct']:+.2f}%[/]",
            f"${s['final_capital']:,.2f}",
        )
    console.print(table)

    winner_color = "green"
    console.print(f"\n[bold {winner_color}]Winner:[/] {report.winner}")
    console.print(f"Delta PnL: {report.rl.total_pnl_pct - report.bb.total_pnl_pct:+.2f}% (rl - bb)")


async def run_rl_walk_forward_cmd(period: str, train_bars: int, test_bars: int, timesteps: int):
    try:
        from agents.python.rl.walk_forward import run_rl_walk_forward
    except ImportError:
        console.print("[red]RL deps not installed. pip install -r requirements-rl.txt[/]")
        return

    syms = settings.symbols
    console.print(
        f"\n[bold]RL walk-forward[/] symbols={len(syms)} period={period} "
        f"train={train_bars} test={test_bars} timesteps={timesteps:,}"
    )

    report = await asyncio.to_thread(
        run_rl_walk_forward,
        syms,
        period,
        train_bars,
        test_bars,
        test_bars,
        timesteps,
    )

    s = report.summary()
    table = Table(title="RL walk-forward summary", box=box.ROUNDED)
    table.add_column("Metric", style="cyan")
    table.add_column("Value", justify="right")
    for k, v in s.items():
        table.add_row(k.replace("_", " ").title(), str(v))
    console.print(table)

    if report.windows:
        w_table = Table(title=f"Windows ({len(report.windows)})", box=box.SIMPLE)
        for col in ["#", "Train", "Test", "Test PnL $", "Trades", "Wins"]:
            w_table.add_column(col, justify="right")
        for i, w in enumerate(report.windows, 1):
            pnl = w.test_result.get("total_pnl", 0)
            color = "green" if pnl > 0 else "red"
            w_table.add_row(
                str(i),
                f"{w.train_start}..{w.train_end}",
                f"{w.test_start}..{w.test_end}",
                f"[{color}]${pnl:+,.2f}[/]",
                str(w.test_result.get("total_trades", 0)),
                str(w.test_result.get("total_wins", 0)),
            )
        console.print(w_table)


async def run_rl_eval_cmd(period: str, symbols: list[str] | None = None):
    try:
        from agents.python.rl.trainer import evaluate, load_historical, load_latest
    except ImportError:
        console.print("[red]RL deps not installed. pip install -r requirements-rl.txt[/]")
        return

    model = load_latest()
    if model is None:
        console.print("[red]No trained model found. Run 'rl-train' first.[/]")
        return

    syms = symbols or settings.symbols
    console.print(f"\n[bold]RL eval[/] symbols={len(syms)} period={period}")
    data = await asyncio.to_thread(load_historical, syms, period)
    results = await asyncio.to_thread(evaluate, model, data)

    table = Table(title="RL evaluation", box=box.ROUNDED)
    for col in ["Symbol", "Trades", "Wins", "Win %", "Total PnL $", "Final Equity $"]:
        table.add_column(col, justify="right")
    for sym, r in results.items():
        color = "green" if r["total_pnl"] >= 0 else "red"
        table.add_row(
            sym,
            str(r["trades"]),
            str(r["wins"]),
            f"{r['win_rate'] * 100:.1f}",
            f"[{color}]${r['total_pnl']:+,.2f}[/]",
            f"${r['final_equity']:,.2f}",
        )
    console.print(table)


async def main():
    parser = argparse.ArgumentParser(description="Stock Trader — Multi-Agent AI System")
    parser.add_argument(
        "command",
        choices=[
            "run",
            "loop",
            "status",
            "check",
            "backtest",
            "dashboard",
            "reset",
            "walk-forward",
            "optimize",
            "correlation",
            "rl-train",
            "rl-eval",
            "rl-walk-forward",
            "rl-ab",
        ],
        help="Command to execute",
    )
    parser.add_argument("--interval", type=int, default=settings.cycle_interval_sec, help="Loop interval in seconds")
    parser.add_argument("--dry-run", action="store_true", help="Analyze without executing trades")
    parser.add_argument("--train-days", type=int, default=90, help="Walk-forward train window")
    parser.add_argument("--test-days", type=int, default=30, help="Walk-forward test window")
    parser.add_argument("--period", default="6mo", help="Backtest period (1mo, 3mo, 6mo, 1y, 2y)")
    parser.add_argument("--save", action="store_true", help="Save backtest results to paper broker DB")
    parser.add_argument("--timesteps", type=int, default=100_000, help="RL training timesteps")
    parser.add_argument("--symbols", type=str, default="", help="Comma-separated symbols override")
    parser.add_argument("--train-ratio", type=float, default=0.7, help="A/B split ratio")
    parser.add_argument(
        "--strategy",
        default="bb_mean_reversion",
        choices=["bb_mean_reversion", "momentum", "momentum_breakout", "bb_regime_filtered"],
        help="Backtest strategy",
    )
    args = parser.parse_args()

    symbols_override = [s.strip().upper() for s in args.symbols.split(",") if s.strip()] or None

    print_banner()

    if args.command == "check":
        await check_dependencies()

    elif args.command == "status":
        await show_status()

    elif args.command == "backtest":
        await run_backtest_cmd(args.period, save=args.save, strategy=args.strategy)

    elif args.command == "walk-forward":
        await run_walk_forward_cmd(args.period, args.train_days, args.test_days)

    elif args.command == "optimize":
        await run_optimize_cmd(args.period)

    elif args.command == "correlation":
        await run_correlation_cmd(args.period)

    elif args.command == "dashboard":
        run_dashboard()

    elif args.command == "reset":
        from agents.python import paper_broker

        paper_broker.reset_account()
        console.print("[green]Account reset to $100,000[/]")

    elif args.command == "run":
        ok = await check_dependencies(dry_run=args.dry_run)
        if not ok:
            console.print("[red]Fix missing dependencies before running[/]")
            return
        await run_cycle(args.dry_run)

    elif args.command == "loop":
        ok = await check_dependencies(dry_run=args.dry_run)
        if not ok:
            console.print("[red]Fix missing dependencies before running[/]")
            return
        await run_loop(args.interval, args.dry_run)

    elif args.command == "rl-train":
        await run_rl_train_cmd(args.period, args.timesteps, symbols_override)

    elif args.command == "rl-eval":
        await run_rl_eval_cmd(args.period, symbols_override)

    elif args.command == "rl-walk-forward":
        await run_rl_walk_forward_cmd(args.period, args.train_days, args.test_days, args.timesteps)

    elif args.command == "rl-ab":
        await run_rl_ab_cmd(args.period, args.train_ratio, args.timesteps, symbols_override)


def cli():
    if len(sys.argv) > 1 and sys.argv[1] == "dashboard":
        print_banner()
        run_dashboard()
        return
    asyncio.run(main())


if __name__ == "__main__":
    cli()
