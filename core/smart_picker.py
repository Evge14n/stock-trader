from __future__ import annotations

from dataclasses import dataclass

import structlog

from agents.python.consensus import (
    compute_consensus,
    regime_ok_for_mean_reversion,
    regime_ok_for_momentum,
)
from agents.python.indicators import _to_df
from agents.strategies.base import get_strategy
from config.settings import settings
from core.state import Analysis, PipelineState, TradeSignal

log = structlog.get_logger(__name__)


@dataclass
class StrategyVote:
    source: str
    action: str
    confidence: float
    reasoning: str = ""
    confluence_voters: int = 1
    confluence_total: int = 1

    def as_dict(self) -> dict:
        return {
            "source": self.source,
            "action": self.action,
            "confidence": round(self.confidence, 3),
            "reasoning": self.reasoning,
            "confluence_voters": self.confluence_voters,
            "confluence_total": self.confluence_total,
        }

    def size_multiplier(self) -> float:
        if self.confluence_total <= 0:
            return 1.0
        ratio = self.confluence_voters / self.confluence_total
        if self.confluence_voters >= 4:
            return 1.3
        if self.confluence_voters == 3 and ratio >= 0.75:
            return 1.15
        if self.confluence_voters == 2:
            return 0.85
        return 1.0


def _llm_vote(symbol: str, state: PipelineState) -> StrategyVote | None:
    analyses = state.analyses.get(symbol, [])
    researcher = next((a for a in reversed(analyses) if a.agent == "researcher"), None)
    if not researcher:
        return None
    if researcher.confidence < settings.researcher_min_confidence:
        return None

    signal = researcher.signal
    if signal in ("buy", "strong_buy"):
        action = "buy"
    elif signal in ("sell", "strong_sell"):
        action = "sell"
    else:
        return None

    if settings.strict_consensus:
        consensus = compute_consensus(analyses)
        if not consensus.passes(settings.consensus_min_agents, settings.consensus_min_alignment):
            return None
        if action == "buy" and consensus.direction != "bullish":
            return None
        if action == "sell" and consensus.direction != "bearish":
            return None

    return StrategyVote(
        source="llm_research",
        action=action,
        confidence=float(researcher.confidence),
        reasoning=f"researcher={signal}, conf={researcher.confidence:.2f}",
    )


def _bb_vote(symbol: str, state: PipelineState) -> StrategyVote | None:
    md = state.market_data.get(symbol)
    if not md or not md.ohlcv:
        return None
    df = _to_df(md.ohlcv)
    if df.empty or len(df) < 30:
        return None

    indicators = state.indicators.get(symbol, [])
    adx_ind = next((i for i in indicators if i.name == "ADX"), None)
    adx = adx_ind.value if adx_ind else 0.0
    if adx > 0 and not regime_ok_for_mean_reversion(adx):
        return None

    strategy = get_strategy("bb_mean_reversion")
    signal = strategy.signal(df, len(df) - 1)
    if signal not in ("buy", "sell"):
        return None

    bb_ind = next((i for i in indicators if i.name == "BB"), None)
    rsi_ind = next((i for i in indicators if i.name == "RSI"), None)
    bb_pos = bb_ind.value if bb_ind else 0.5
    rsi_val = rsi_ind.value if rsi_ind else 50.0

    if signal == "buy":
        extremity = max(0.0, (0.25 - bb_pos) / 0.25) + max(0.0, (35 - rsi_val) / 35)
    else:
        extremity = max(0.0, (bb_pos - 0.85) / 0.15) + max(0.0, (rsi_val - 70) / 30)
    confidence = min(0.95, 0.55 + extremity * 0.2)

    return StrategyVote(
        source="bb_mean_reversion",
        action=signal,
        confidence=round(confidence, 3),
        reasoning=f"bb_pos={bb_pos:.2f}, rsi={rsi_val:.1f}, adx={adx:.1f}",
    )


def _momentum_vote(symbol: str, state: PipelineState) -> StrategyVote | None:
    md = state.market_data.get(symbol)
    if not md or not md.ohlcv:
        return None
    df = _to_df(md.ohlcv)
    if df.empty or len(df) < 30:
        return None

    indicators = state.indicators.get(symbol, [])
    adx_ind = next((i for i in indicators if i.name == "ADX"), None)
    adx = adx_ind.value if adx_ind else 0.0
    if adx > 0 and not regime_ok_for_momentum(adx):
        return None

    strategy = get_strategy("momentum")
    signal = strategy.signal(df, len(df) - 1)
    if signal not in ("buy", "sell"):
        return None

    macd_ind = next((i for i in indicators if i.name == "MACD"), None)
    macd_hist = macd_ind.value if macd_ind else 0.0
    confidence = min(0.92, 0.6 + min(adx / 50.0, 0.3) + (0.05 if abs(macd_hist) > 0.1 else 0))

    return StrategyVote(
        source="momentum",
        action=signal,
        confidence=round(confidence, 3),
        reasoning=f"adx={adx:.1f}, macd_hist={macd_hist:.3f}",
    )


def _rs_vote(symbol: str, state: PipelineState) -> StrategyVote | None:
    if not state.symbols or len(state.symbols) < 4:
        return None

    try:
        from agents.python.relative_strength import rank_for

        rank = rank_for(symbol, state.symbols)
    except Exception:
        return None

    if rank is None:
        return None

    if rank.percentile >= 0.7:
        action = "buy"
    elif rank.percentile <= 0.3:
        action = "sell"
    else:
        return None

    strength = abs(rank.percentile - 0.5) * 2.0
    confidence = min(0.88, 0.6 + strength * 0.25)

    return StrategyVote(
        source="relative_strength",
        action=action,
        confidence=round(confidence, 3),
        reasoning=f"rank={rank.rank}/{len(state.symbols)}, 20d_ret={rank.return_pct:+.2f}%",
    )


def _forecaster_vote(symbol: str, state: PipelineState) -> StrategyVote | None:
    from agents.python.forecaster import _model_path, predict_next_return

    if not _model_path(symbol).exists():
        return None

    md = state.market_data.get(symbol)
    if not md or md.price <= 0:
        return None

    try:
        pred = predict_next_return(symbol)
    except Exception:
        return None

    if "error" in pred:
        return None

    pred_pct = pred.get("predicted_return_pct", 0.0)
    if abs(pred_pct) < 1.0:
        return None

    action = "buy" if pred_pct > 0 else "sell"
    dir_accuracy = pred.get("model_accuracy", 0.0)
    if dir_accuracy < 0.5:
        return None

    magnitude = min(abs(pred_pct) / 3.0, 0.3)
    confidence = min(0.9, dir_accuracy + magnitude)

    return StrategyVote(
        source="forecaster_mlp",
        action=action,
        confidence=round(confidence, 3),
        reasoning=f"pred={pred_pct:+.2f}%, dir_acc={dir_accuracy:.1f}%",
    )


def _rl_vote(symbol: str, state: PipelineState) -> StrategyVote | None:
    try:
        from agents.python.rl import agent as rl_agent
    except ImportError:
        return None

    model = rl_agent._load_model()
    if model is None:
        return None

    try:
        signal = rl_agent._signal_for(symbol, state, model)
    except Exception:
        return None
    if signal is None:
        return None

    return StrategyVote(
        source="rl_ppo",
        action=signal.action,
        confidence=float(signal.confidence),
        reasoning=signal.reasoning,
    )


def gather_votes(symbol: str, state: PipelineState) -> list[StrategyVote]:
    votes: list[StrategyVote] = []
    for fn in (_llm_vote, _bb_vote, _momentum_vote, _rl_vote, _forecaster_vote, _rs_vote):
        try:
            v = fn(symbol, state)
        except Exception as e:
            log.warning("smart_picker_voter_error", fn=fn.__name__, symbol=symbol, error=str(e))
            v = None
        if v is not None:
            votes.append(v)

    try:
        from agents.python.voter_stats import apply_weights_to_votes

        votes = apply_weights_to_votes(votes)
    except Exception as e:
        log.warning("voter_weight_apply_failed", error=str(e))

    try:
        from agents.python.market_regime import apply_regime_to_votes

        votes = apply_regime_to_votes(votes, state.symbols)
    except Exception as e:
        log.warning("regime_apply_failed", error=str(e))
    return votes


def pick_best(votes: list[StrategyVote]) -> StrategyVote | None:
    filtered = [v for v in votes if v.confidence >= settings.smart_min_confidence]
    if not filtered:
        return None

    buys = [v for v in filtered if v.action == "buy"]
    sells = [v for v in filtered if v.action == "sell"]

    if len(buys) >= settings.smart_min_voters and len(buys) >= len(sells):
        best = max(buys, key=lambda v: v.confidence)
        avg_conf = sum(v.confidence for v in buys) / len(buys)
        return StrategyVote(
            source=f"consensus_{len(buys)}/{len(filtered)}:{best.source}",
            action="buy",
            confidence=round(avg_conf, 3),
            reasoning="; ".join(f"{v.source}:{v.confidence:.2f}" for v in buys),
            confluence_voters=len(buys),
            confluence_total=len(filtered),
        )

    if len(sells) >= settings.smart_min_voters and len(sells) > len(buys):
        best = max(sells, key=lambda v: v.confidence)
        avg_conf = sum(v.confidence for v in sells) / len(sells)
        return StrategyVote(
            source=f"consensus_{len(sells)}/{len(filtered)}:{best.source}",
            action="sell",
            confidence=round(avg_conf, 3),
            reasoning="; ".join(f"{v.source}:{v.confidence:.2f}" for v in sells),
            confluence_voters=len(sells),
            confluence_total=len(filtered),
        )

    return None


def _to_trade_signal(symbol: str, vote: StrategyVote, state: PipelineState) -> TradeSignal | None:
    md = state.market_data.get(symbol)
    if not md or md.price <= 0:
        return None

    indicators = state.indicators.get(symbol, [])
    atr_ind = next((i for i in indicators if i.name == "ATR"), None)
    atr = atr_ind.value if atr_ind else 0.0

    if atr > 0:
        atr_pct = atr / md.price
        stop_pct = max(0.015, min(0.05, atr_pct * 1.5))
        tp_pct = max(0.03, min(0.12, atr_pct * 3.0))
    else:
        stop_pct = 0.03
        tp_pct = 0.06

    size_mult = vote.size_multiplier()

    corr_factor = 1.0
    corr_info = ""
    if settings.correlation_cap:
        try:
            from agents.python import paper_broker
            from agents.python.correlation_sizing import size_factor

            held = [p["symbol"] for p in paper_broker.list_positions() if p.get("symbol") != symbol]
            if held:
                corr_factor, max_corr = size_factor(
                    symbol,
                    held,
                    threshold=settings.correlation_threshold,
                    max_cut=settings.correlation_min_factor,
                )
                if corr_factor < 1.0:
                    corr_info = f" corr×{corr_factor:.2f}(max={max_corr:.2f})"
        except Exception as e:
            log.warning("correlation_sizing_error", symbol=symbol, error=str(e))

    final_mult = size_mult * corr_factor
    risk_amount = settings.max_position_size * settings.risk_per_trade * final_mult
    risk_per_share = md.price * stop_pct
    if risk_per_share <= 0:
        return None
    qty = int(risk_amount / risk_per_share)
    max_shares = int(settings.max_position_size * final_mult / md.price)
    qty = min(qty, max_shares)
    if qty <= 0:
        return None

    if vote.action == "buy":
        sl = round(md.price * (1 - stop_pct), 2)
        tp = round(md.price * (1 + tp_pct), 2)
    else:
        sl = round(md.price * (1 + stop_pct), 2)
        tp = round(md.price * (1 - tp_pct), 2)

    return TradeSignal(
        symbol=symbol,
        action=vote.action,
        quantity=qty,
        entry_price=md.price,
        stop_loss=sl,
        take_profit=tp,
        confidence=vote.confidence,
        reasoning=f"[{vote.source}] size×{size_mult:.2f}{corr_info} {vote.reasoning[:210]}",
    )


async def smart_decide(state: PipelineState) -> PipelineState:
    for symbol in state.symbols:
        votes = gather_votes(symbol, state)
        if votes:
            record = Analysis(
                agent="smart_picker",
                symbol=symbol,
                signal=f"votes={len(votes)}",
                confidence=max(v.confidence for v in votes),
                reasoning="; ".join(f"{v.source}:{v.action}@{v.confidence:.2f}" for v in votes),
            )
            state.analyses.setdefault(symbol, []).append(record)

        best = pick_best(votes)
        if best is None:
            continue

        signal = _to_trade_signal(symbol, best, state)
        if signal:
            state.signals.append(signal)
    return state
