from __future__ import annotations
import asyncio
import argparse
import sys
import uuid
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

from config.settings import settings
from core import llm_client
from core.orchestrator import build_graph
from agents.python import portfolio_tracker

console = Console()


def print_banner():
    console.print(Panel.fit(
        "[bold cyan]Stock Trader[/] — Multi-Agent AI Trading System\n"
        f"Model: {settings.ollama_model} | Symbols: {len(settings.symbols)} | Paper Trading",
        border_style="cyan",
    ))


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
                color = "green" if "bull" in signal or "buy" in signal else "red" if "bear" in signal or "sell" in signal else "yellow"
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

    console.print(Panel.fit(
        f"Equity: ${account.get('equity', 0):,.2f}\n"
        f"Cash: ${account.get('cash', 0):,.2f}\n"
        f"Positions: {len(positions)}\n"
        f"Unrealized P/L: ${snap.get('total_unrealized_pl', 0):,.2f}",
        title="Portfolio",
        border_style="green",
    ))

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
    console.print(f"\n  Total trades: {stats['total_trades']} | Win rate: {stats['win_rate']:.1%} | Total P/L: ${stats['total_pl']:+.2f}")


async def run_backtest_cmd(period: str, symbols: list[str] | None = None):
    from agents.python.backtest import run_backtest

    syms = symbols or settings.symbols
    console.print(f"\n[bold]Backtest[/] on {len(syms)} symbols, period={period}")
    console.print(f"Symbols: {', '.join(syms)}")
    console.print("[dim]Running historical simulation...[/]\n")

    result = await asyncio.to_thread(run_backtest, syms, 100_000.0, period)
    summary = result.summary()

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


async def main():
    parser = argparse.ArgumentParser(description="Stock Trader — Multi-Agent AI System")
    parser.add_argument("command", choices=["run", "loop", "status", "check", "backtest", "dashboard", "reset"],
                        help="Command to execute")
    parser.add_argument("--interval", type=int, default=settings.cycle_interval_sec, help="Loop interval in seconds")
    parser.add_argument("--dry-run", action="store_true", help="Analyze without executing trades")
    parser.add_argument("--period", default="6mo", help="Backtest period (1mo, 3mo, 6mo, 1y, 2y)")
    args = parser.parse_args()

    print_banner()

    if args.command == "check":
        await check_dependencies()

    elif args.command == "status":
        await show_status()

    elif args.command == "backtest":
        await run_backtest_cmd(args.period)

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


def cli():
    if len(sys.argv) > 1 and sys.argv[1] == "dashboard":
        print_banner()
        run_dashboard()
        return
    asyncio.run(main())


if __name__ == "__main__":
    cli()
