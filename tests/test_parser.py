from core.parser import parse_confidence, parse_response, parse_signal


def test_parse_signal_from_valid_json():
    response = '{"signal": "bullish", "confidence": 0.8, "reasoning": "strong setup"}'
    assert parse_signal(response) == "bullish"


def test_parse_signal_from_text_fallback():
    response = "Looking at the indicators, this is clearly bullish"
    assert parse_signal(response) == "bullish"


def test_parse_signal_bearish_from_json():
    response = '{"signal":"bearish","confidence":0.7}'
    assert parse_signal(response) == "bearish"


def test_parse_signal_strong_buy():
    response = "signal: strong buy, confidence: high"
    assert parse_signal(response) == "strong_buy"


def test_parse_signal_default_on_garbage():
    response = "blah blah nonsense"
    assert parse_signal(response, default_signal="neutral") == "neutral"


def test_parse_confidence_from_json():
    response = '{"signal": "bullish", "confidence": 0.75}'
    assert parse_confidence(response) == 0.75


def test_parse_confidence_from_percent():
    response = "I am 80% confident this is bullish"
    assert parse_confidence(response) == 0.80


def test_parse_confidence_from_marker():
    response = "Strong bullish signal here"
    assert parse_confidence(response) == 0.8


def test_parse_confidence_capped_at_1():
    response = '{"confidence": 1.5}'
    assert parse_confidence(response) == 1.0


def test_parse_confidence_non_negative():
    response = '{"confidence": -0.5}'
    assert parse_confidence(response) == 0.0


def test_parse_response_combined():
    response = '{"signal": "buy", "confidence": 0.85, "reasoning": "solid"}'
    signal, conf = parse_response(response)
    assert signal == "buy"
    assert conf == 0.85


def test_parse_response_mixed_format():
    response = "My analysis: signal = bullish with confidence 0.72"
    signal, conf = parse_response(response)
    assert signal == "bullish"
    assert conf == 0.72
