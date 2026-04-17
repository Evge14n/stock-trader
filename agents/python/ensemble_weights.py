from __future__ import annotations

import sqlite3
from pathlib import Path

import orjson

from agents.python import paper_broker
from config.settings import settings

DEFAULT_WEIGHTS = {
    "technical_analyst": 0.15,
    "news_analyst": 0.10,
    "sector_tech": 0.08,
    "sector_finance": 0.08,
    "sector_healthcare": 0.08,
    "sector_energy": 0.08,
    "sector_consumer_discretionary": 0.08,
    "sector_consumer_staples": 0.08,
    "sector_commodities": 0.08,
    "sector_crypto": 0.08,
    "sector_unknown": 0.03,
    "fundamental_analyst": 0.12,
    "momentum_analyst": 0.10,
    "volatility_analyst": 0.08,
    "pattern_recognizer": 0.12,
    "multi_timeframe": 0.15,
    "debate_judge": 0.20,
    "researcher": 0.18,
}


def _weights_path() -> Path:
    return settings.data_dir / "ensemble_weights.json"


def load_weights() -> dict[str, float]:
    path = _weights_path()
    if not path.exists():
        return DEFAULT_WEIGHTS.copy()
    try:
        data = orjson.loads(path.read_bytes())
        merged = DEFAULT_WEIGHTS.copy()
        merged.update(data.get("weights", {}))
        return merged
    except Exception:
        return DEFAULT_WEIGHTS.copy()


def save_weights(weights: dict[str, float], stats: dict | None = None) -> None:
    path = _weights_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"weights": weights, "stats": stats or {}}
    path.write_bytes(orjson.dumps(payload, option=orjson.OPT_INDENT_2))


def _signal_direction(signal: str) -> int:
    bullish = {"bullish", "buy", "strong_buy"}
    bearish = {"bearish", "sell", "strong_sell"}
    if signal in bullish:
        return 1
    if signal in bearish:
        return -1
    return 0


def _trade_direction(pnl: float) -> int:
    if pnl > 0:
        return 1
    if pnl < 0:
        return -1
    return 0


def _load_trades_with_analyses() -> list[dict]:
    with sqlite3.connect(paper_broker._db_path()) as conn:
        conn.row_factory = sqlite3.Row
        trades = conn.execute(
            "SELECT * FROM trades WHERE closed_at IS NOT NULL AND pnl IS NOT NULL ORDER BY id DESC LIMIT 100"
        ).fetchall()
    return [dict(t) for t in trades]


def recompute_weights(agent_decisions_log: list[dict] | None = None) -> dict[str, float]:
    trades = _load_trades_with_analyses()

    if len(trades) < 10:
        return DEFAULT_WEIGHTS.copy()

    agent_scores: dict[str, dict] = {}
    log = agent_decisions_log or []

    for trade in trades:
        symbol = trade["symbol"]
        trade_dir = _trade_direction(trade["pnl"])
        if trade_dir == 0:
            continue

        matching = [d for d in log if d.get("symbol") == symbol and d.get("trade_id") == trade["id"]]
        for decision in matching:
            for agent, info in (decision.get("agents") or {}).items():
                sig_dir = _signal_direction(info.get("signal", "neutral"))
                if agent not in agent_scores:
                    agent_scores[agent] = {"correct": 0, "total": 0, "confidence_sum": 0}

                agent_scores[agent]["total"] += 1
                if sig_dir == trade_dir:
                    agent_scores[agent]["correct"] += 1
                agent_scores[agent]["confidence_sum"] += info.get("confidence", 0.5)

    new_weights = DEFAULT_WEIGHTS.copy()
    for agent, score in agent_scores.items():
        if score["total"] < 5:
            continue
        accuracy = score["correct"] / score["total"]
        baseline = DEFAULT_WEIGHTS.get(agent, 0.10)
        new_weights[agent] = round(baseline * (0.5 + accuracy), 4)

    total = sum(new_weights.values())
    if total > 0:
        new_weights = {k: round(v / total, 4) for k, v in new_weights.items()}

    stats = {
        "sample_trades": len(trades),
        "agents_with_data": len([a for a, s in agent_scores.items() if s["total"] >= 5]),
        "accuracies": {a: round(s["correct"] / s["total"], 3) for a, s in agent_scores.items() if s["total"] >= 5},
    }
    save_weights(new_weights, stats=stats)

    return new_weights


def weighted_score(analyses: list[dict], weights: dict[str, float] | None = None) -> float:
    if weights is None:
        weights = load_weights()

    total_score = 0.0
    total_weight = 0.0

    for a in analyses:
        agent = a.get("agent", "")
        weight = weights.get(agent, 0.05)
        direction = _signal_direction(a.get("signal", "neutral"))
        confidence = a.get("confidence", 0.5)
        total_score += direction * confidence * weight
        total_weight += weight * confidence

    if total_weight == 0:
        return 0.0
    return total_score / total_weight
