from agents.python.explainer import counterfactual, explain_decision
from core.state import Analysis, PipelineState


def _make_state_with_analyses(symbol: str, analyses: list[Analysis]) -> PipelineState:
    ps = PipelineState(symbols=[symbol])
    ps.analyses[symbol] = analyses
    return ps


def test_explain_decision_no_data():
    ps = PipelineState(symbols=["AAPL"])
    result = explain_decision("AAPL", ps)
    assert result["decision"] == "no_data"


def test_explain_decision_all_bullish():
    analyses = [
        Analysis(agent="technical_analyst", symbol="AAPL", signal="bullish", confidence=0.8),
        Analysis(agent="fundamental_analyst", symbol="AAPL", signal="bullish", confidence=0.7),
        Analysis(agent="momentum_analyst", symbol="AAPL", signal="bullish", confidence=0.8),
    ]
    ps = _make_state_with_analyses("AAPL", analyses)
    result = explain_decision("AAPL", ps)
    assert result["decision"] == "buy"
    assert result["final_score"] > 0.3
    assert len(result["contributions"]) == 3


def test_explain_decision_all_bearish():
    analyses = [
        Analysis(agent="technical_analyst", symbol="AAPL", signal="bearish", confidence=0.8),
        Analysis(agent="news_analyst", symbol="AAPL", signal="bearish", confidence=0.9),
    ]
    ps = _make_state_with_analyses("AAPL", analyses)
    result = explain_decision("AAPL", ps)
    assert result["decision"] == "sell"
    assert result["final_score"] < -0.3


def test_explain_decision_mixed():
    analyses = [
        Analysis(agent="technical_analyst", symbol="AAPL", signal="bullish", confidence=0.5),
        Analysis(agent="news_analyst", symbol="AAPL", signal="bearish", confidence=0.5),
    ]
    ps = _make_state_with_analyses("AAPL", analyses)
    result = explain_decision("AAPL", ps)
    assert result["decision"] == "hold"


def test_explain_top_drivers_sorted():
    analyses = [
        Analysis(agent="technical_analyst", symbol="X", signal="bullish", confidence=0.9),
        Analysis(agent="volatility_analyst", symbol="X", signal="neutral", confidence=0.3),
        Analysis(agent="momentum_analyst", symbol="X", signal="bullish", confidence=0.8),
        Analysis(agent="sector_unknown", symbol="X", signal="neutral", confidence=0.2),
    ]
    ps = _make_state_with_analyses("X", analyses)
    result = explain_decision("X", ps)
    drivers = result["top_drivers"]
    for i in range(len(drivers) - 1):
        assert abs(drivers[i]["contribution"]) >= abs(drivers[i + 1]["contribution"])


def test_counterfactual_flips_signal():
    analyses = [
        Analysis(agent="technical_analyst", symbol="AAPL", signal="bullish", confidence=0.9),
        Analysis(agent="news_analyst", symbol="AAPL", signal="bullish", confidence=0.9),
    ]
    ps = _make_state_with_analyses("AAPL", analyses)
    result = counterfactual("AAPL", ps, flip_agent="technical_analyst")
    assert result["flipped_agent"] == "technical_analyst"
    assert "new_decision" in result
