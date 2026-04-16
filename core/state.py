from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class MarketData:
    symbol: str = ""
    price: float = 0.0
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    close: float = 0.0
    volume: int = 0
    ohlcv: list[dict] = field(default_factory=list)
    timestamp: str = ""


@dataclass
class Indicator:
    name: str = ""
    value: float = 0.0
    signal: str = ""
    details: dict = field(default_factory=dict)


@dataclass
class NewsItem:
    headline: str = ""
    source: str = ""
    url: str = ""
    sentiment: float = 0.0
    timestamp: str = ""


@dataclass
class Analysis:
    agent: str = ""
    symbol: str = ""
    signal: str = ""
    confidence: float = 0.0
    reasoning: str = ""
    timestamp: str = ""


@dataclass
class TradeSignal:
    symbol: str = ""
    action: str = ""
    quantity: int = 0
    entry_price: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0
    confidence: float = 0.0
    reasoning: str = ""


@dataclass
class RiskCheck:
    passed: bool = False
    reason: str = ""
    checks: dict = field(default_factory=dict)


@dataclass
class PipelineState:
    cycle_id: str = ""
    symbols: list[str] = field(default_factory=list)
    market_data: dict[str, MarketData] = field(default_factory=dict)
    indicators: dict[str, list[Indicator]] = field(default_factory=dict)
    news: dict[str, list[NewsItem]] = field(default_factory=dict)
    analyses: dict[str, list[Analysis]] = field(default_factory=dict)
    signals: list[TradeSignal] = field(default_factory=list)
    risk_checks: list[RiskCheck] = field(default_factory=list)
    approved_trades: list[TradeSignal] = field(default_factory=list)
    execution_results: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    dry_run: bool = False
    started_at: str = field(default_factory=lambda: datetime.now().isoformat())
    completed_at: str = ""

    def add_error(self, msg: str):
        self.errors.append(f"[{datetime.now().isoformat()}] {msg}")
