from __future__ import annotations

from datetime import datetime
from typing import Any

from langgraph.graph import END, StateGraph

from agents.llm.debate import analyze as debate_analyze
from agents.llm.fundamental_analyst import analyze as fundamental_analyze
from agents.llm.momentum_analyst import analyze as momentum_analyze
from agents.llm.news_analyst import analyze as news_analyze
from agents.llm.researcher import synthesize
from agents.llm.sector_analyst import analyze as sector_analyze
from agents.llm.technical_analyst import analyze as technical_analyze
from agents.llm.trader import decide
from agents.llm.volatility_analyst import analyze as volatility_analyze
from agents.python import portfolio_tracker
from agents.python.data_collector import collect_all
from agents.python.indicators import compute_all
from agents.python.multi_timeframe import analyze as multi_tf_analyze
from agents.python.news_fetcher import collect_news
from agents.python.order_manager import execute_trades
from agents.python.patterns import analyze as pattern_analyze
from agents.python.risk_validator import validate
from agents.python.watchlist_scanner import filter_watchlist
from core.state import PipelineState


def _wrap(fn, name: str):
    async def wrapped(state: dict[str, Any]) -> dict[str, Any]:
        ps = _dict_to_state(state)
        try:
            ps = await fn(ps)
        except Exception as e:
            ps.add_error(f"{name}: {type(e).__name__}: {e}")
        return _state_to_dict(ps)

    return wrapped


async def node_collect_data(state: dict[str, Any]) -> dict[str, Any]:
    ps = _dict_to_state(state)
    ps = await collect_all(ps)
    return _state_to_dict(ps)


async def node_collect_news(state: dict[str, Any]) -> dict[str, Any]:
    ps = _dict_to_state(state)
    ps = await collect_news(ps)
    return _state_to_dict(ps)


async def node_compute_indicators(state: dict[str, Any]) -> dict[str, Any]:
    ps = _dict_to_state(state)
    ps = await compute_all(ps)
    return _state_to_dict(ps)


async def node_technical_analysis(state: dict[str, Any]) -> dict[str, Any]:
    ps = _dict_to_state(state)
    ps = await technical_analyze(ps)
    return _state_to_dict(ps)


async def node_news_analysis(state: dict[str, Any]) -> dict[str, Any]:
    ps = _dict_to_state(state)
    ps = await news_analyze(ps)
    return _state_to_dict(ps)


async def node_sector_analysis(state: dict[str, Any]) -> dict[str, Any]:
    ps = _dict_to_state(state)
    ps = await sector_analyze(ps)
    return _state_to_dict(ps)


async def node_fundamental_analysis(state: dict[str, Any]) -> dict[str, Any]:
    ps = _dict_to_state(state)
    ps = await fundamental_analyze(ps)
    return _state_to_dict(ps)


async def node_momentum_analysis(state: dict[str, Any]) -> dict[str, Any]:
    ps = _dict_to_state(state)
    ps = await momentum_analyze(ps)
    return _state_to_dict(ps)


async def node_volatility_analysis(state: dict[str, Any]) -> dict[str, Any]:
    ps = _dict_to_state(state)
    ps = await volatility_analyze(ps)
    return _state_to_dict(ps)


async def node_filter_watchlist(state: dict[str, Any]) -> dict[str, Any]:
    ps = _dict_to_state(state)
    ps = await filter_watchlist(ps)
    return _state_to_dict(ps)


async def node_research(state: dict[str, Any]) -> dict[str, Any]:
    ps = _dict_to_state(state)
    ps = await synthesize(ps)
    return _state_to_dict(ps)


async def node_trade_decision(state: dict[str, Any]) -> dict[str, Any]:
    ps = _dict_to_state(state)
    ps = await decide(ps)
    return _state_to_dict(ps)


async def node_risk_check(state: dict[str, Any]) -> dict[str, Any]:
    ps = _dict_to_state(state)
    ps = await validate(ps)
    return _state_to_dict(ps)


async def node_execute(state: dict[str, Any]) -> dict[str, Any]:
    ps = _dict_to_state(state)
    if ps.approved_trades and not ps.dry_run:
        ps = await execute_trades(ps)
        for result in ps.execution_results:
            portfolio_tracker.log_trade(result)
    elif ps.approved_trades and ps.dry_run:
        for sig in ps.approved_trades:
            ps.execution_results.append(
                {
                    "symbol": sig.symbol,
                    "side": sig.action,
                    "qty": sig.quantity,
                    "status": "DRY_RUN",
                    "entry": sig.entry_price,
                    "stop_loss": sig.stop_loss,
                    "take_profit": sig.take_profit,
                }
            )
    if not ps.dry_run:
        try:
            snap = portfolio_tracker.snapshot()
            portfolio_tracker.save_snapshot(snap)
        except Exception:
            pass
    ps.completed_at = datetime.now().isoformat()
    return _state_to_dict(ps)


def should_continue(state: dict[str, Any]) -> str:
    signals = state.get("signals", [])
    if not signals:
        return "skip_execution"
    return "execute"


def build_graph() -> StateGraph:
    graph = StateGraph(dict)

    graph.add_node("collect_data", _wrap(collect_all, "collect_data"))
    graph.add_node("collect_news", _wrap(collect_news, "collect_news"))
    graph.add_node("compute_indicators", _wrap(compute_all, "compute_indicators"))
    graph.add_node("filter_watchlist", _wrap(filter_watchlist, "filter_watchlist"))
    graph.add_node("pattern_recognizer", _wrap(pattern_analyze, "pattern_recognizer"))
    graph.add_node("multi_timeframe", _wrap(multi_tf_analyze, "multi_timeframe"))
    graph.add_node("technical_analysis", _wrap(technical_analyze, "technical_analysis"))
    graph.add_node("news_analysis", _wrap(news_analyze, "news_analysis"))
    graph.add_node("sector_analysis", _wrap(sector_analyze, "sector_analysis"))
    graph.add_node("fundamental_analysis", _wrap(fundamental_analyze, "fundamental_analysis"))
    graph.add_node("momentum_analysis", _wrap(momentum_analyze, "momentum_analysis"))
    graph.add_node("volatility_analysis", _wrap(volatility_analyze, "volatility_analysis"))
    graph.add_node("debate", _wrap(debate_analyze, "debate"))
    graph.add_node("research", _wrap(synthesize, "research"))
    graph.add_node("trade_decision", _wrap(decide, "trade_decision"))
    graph.add_node("risk_check", _wrap(validate, "risk_check"))
    graph.add_node("execute", node_execute)

    graph.set_entry_point("collect_data")
    graph.add_edge("collect_data", "collect_news")
    graph.add_edge("collect_news", "compute_indicators")
    graph.add_edge("compute_indicators", "filter_watchlist")
    graph.add_edge("filter_watchlist", "pattern_recognizer")
    graph.add_edge("pattern_recognizer", "multi_timeframe")
    graph.add_edge("multi_timeframe", "technical_analysis")
    graph.add_edge("technical_analysis", "news_analysis")
    graph.add_edge("news_analysis", "sector_analysis")
    graph.add_edge("sector_analysis", "fundamental_analysis")
    graph.add_edge("fundamental_analysis", "momentum_analysis")
    graph.add_edge("momentum_analysis", "volatility_analysis")
    graph.add_edge("volatility_analysis", "debate")
    graph.add_edge("debate", "research")
    graph.add_edge("research", "trade_decision")

    graph.add_conditional_edges(
        "trade_decision",
        should_continue,
        {
            "execute": "risk_check",
            "skip_execution": "execute",
        },
    )
    graph.add_edge("risk_check", "execute")
    graph.add_edge("execute", END)

    return graph


def _state_to_dict(ps: PipelineState) -> dict[str, Any]:
    from dataclasses import asdict

    return asdict(ps)


def _dict_to_state(d: dict[str, Any]) -> PipelineState:
    from core.state import (
        Analysis,
        Indicator,
        MarketData,
        NewsItem,
        PipelineState,
        RiskCheck,
        TradeSignal,
    )

    ps = PipelineState()
    ps.cycle_id = d.get("cycle_id", "")
    ps.symbols = d.get("symbols", [])
    ps.errors = d.get("errors", [])
    ps.dry_run = d.get("dry_run", False)
    ps.started_at = d.get("started_at", "")
    ps.completed_at = d.get("completed_at", "")

    for sym, md in d.get("market_data", {}).items():
        if isinstance(md, MarketData):
            ps.market_data[sym] = md
        elif isinstance(md, dict):
            ps.market_data[sym] = MarketData(**md)

    for sym, inds in d.get("indicators", {}).items():
        ps.indicators[sym] = []
        for ind in inds:
            if isinstance(ind, Indicator):
                ps.indicators[sym].append(ind)
            elif isinstance(ind, dict):
                ps.indicators[sym].append(Indicator(**ind))

    for sym, news_list in d.get("news", {}).items():
        ps.news[sym] = []
        for n in news_list:
            if isinstance(n, NewsItem):
                ps.news[sym].append(n)
            elif isinstance(n, dict):
                ps.news[sym].append(NewsItem(**n))

    for sym, analyses in d.get("analyses", {}).items():
        ps.analyses[sym] = []
        for a in analyses:
            if isinstance(a, Analysis):
                ps.analyses[sym].append(a)
            elif isinstance(a, dict):
                ps.analyses[sym].append(Analysis(**a))

    for sig in d.get("signals", []):
        if isinstance(sig, TradeSignal):
            ps.signals.append(sig)
        elif isinstance(sig, dict):
            ps.signals.append(TradeSignal(**sig))

    for rc in d.get("risk_checks", []):
        if isinstance(rc, RiskCheck):
            ps.risk_checks.append(rc)
        elif isinstance(rc, dict):
            ps.risk_checks.append(RiskCheck(**rc))

    for at in d.get("approved_trades", []):
        if isinstance(at, TradeSignal):
            ps.approved_trades.append(at)
        elif isinstance(at, dict):
            ps.approved_trades.append(TradeSignal(**at))

    ps.execution_results = d.get("execution_results", [])

    return ps
