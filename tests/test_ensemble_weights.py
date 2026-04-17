from agents.python.ensemble_weights import DEFAULT_WEIGHTS, _signal_direction, load_weights, weighted_score


def test_default_weights_sum_reasonable():
    assert sum(DEFAULT_WEIGHTS.values()) > 0
    assert all(v > 0 for v in DEFAULT_WEIGHTS.values())


def test_load_weights_returns_defaults_without_file():
    weights = load_weights()
    assert "technical_analyst" in weights
    assert "researcher" in weights


def test_signal_direction():
    assert _signal_direction("bullish") == 1
    assert _signal_direction("buy") == 1
    assert _signal_direction("strong_buy") == 1
    assert _signal_direction("bearish") == -1
    assert _signal_direction("sell") == -1
    assert _signal_direction("strong_sell") == -1
    assert _signal_direction("neutral") == 0
    assert _signal_direction("hold") == 0


def test_weighted_score_all_bullish():
    analyses = [
        {"agent": "technical_analyst", "signal": "bullish", "confidence": 0.8},
        {"agent": "news_analyst", "signal": "bullish", "confidence": 0.7},
        {"agent": "researcher", "signal": "buy", "confidence": 0.9},
    ]
    score = weighted_score(analyses)
    assert score > 0


def test_weighted_score_all_bearish():
    analyses = [
        {"agent": "technical_analyst", "signal": "bearish", "confidence": 0.8},
        {"agent": "researcher", "signal": "sell", "confidence": 0.9},
    ]
    score = weighted_score(analyses)
    assert score < 0


def test_weighted_score_mixed():
    analyses = [
        {"agent": "technical_analyst", "signal": "bullish", "confidence": 0.5},
        {"agent": "news_analyst", "signal": "bearish", "confidence": 0.5},
    ]
    score = weighted_score(analyses)
    assert abs(score) < 0.5


def test_weighted_score_empty():
    assert weighted_score([]) == 0.0


def test_weighted_score_neutrals():
    analyses = [
        {"agent": "technical_analyst", "signal": "neutral", "confidence": 0.5},
    ]
    score = weighted_score(analyses)
    assert score == 0.0
