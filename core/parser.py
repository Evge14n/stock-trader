from __future__ import annotations

import re

import orjson


def parse_signal(response: str, default_signal: str = "neutral") -> str:
    cleaned = response.lower().strip()

    try:
        match = re.search(r"\{[^{}]*\}", cleaned, re.DOTALL)
        if match:
            data = orjson.loads(match.group().encode())
            if isinstance(data, dict) and "signal" in data:
                sig = str(data["signal"]).lower().strip()
                if sig in {"bullish", "bearish", "neutral", "buy", "sell", "hold", "strong_buy", "strong_sell"}:
                    return sig
    except Exception:
        pass

    patterns = [
        (r"signal[:\s]+['\"]?(bullish|bearish|neutral|buy|sell|hold|strong[_\s]?buy|strong[_\s]?sell)", 1),
        (r"\bstrong[_\s]buy\b", "strong_buy"),
        (r"\bstrong[_\s]sell\b", "strong_sell"),
        (r"\bbullish\b", "bullish"),
        (r"\bbearish\b", "bearish"),
        (r"\bneutral\b", "neutral"),
        (r"\bbuy\b", "buy"),
        (r"\bsell\b", "sell"),
        (r"\bhold\b", "hold"),
    ]

    for pattern, group_or_value in patterns:
        match = re.search(pattern, cleaned)
        if match:
            if isinstance(group_or_value, int):
                raw = match.group(group_or_value)
                return raw.replace(" ", "_").replace("-", "_")
            return group_or_value

    return default_signal


def parse_confidence(response: str, default: float = 0.5) -> float:
    try:
        match = re.search(r"\{[^{}]*\}", response, re.DOTALL)
        if match:
            data = orjson.loads(match.group().encode())
            if isinstance(data, dict) and "confidence" in data:
                val = float(data["confidence"])
                return max(0.0, min(1.0, val))
    except Exception:
        pass

    patterns = [
        r"confidence[:\s]+(\d*\.?\d+)",
        r"(\d{1,3})\s*%",
        r"confidence\s+[=:]\s+(\d*\.?\d+)",
    ]

    for pattern in patterns:
        match = re.search(pattern, response.lower())
        if match:
            try:
                val = float(match.group(1))
                if val > 1:
                    val = val / 100
                return max(0.0, min(1.0, val))
            except ValueError:
                continue

    markers = {
        "high confidence": 0.85,
        "very strong": 0.9,
        "strong": 0.8,
        "moderate": 0.6,
        "weak": 0.35,
        "low confidence": 0.3,
        "uncertain": 0.3,
    }
    for marker, val in markers.items():
        if marker in response.lower():
            return val

    return default


def parse_response(
    response: str, default_signal: str = "neutral", default_confidence: float = 0.5
) -> tuple[str, float]:
    return parse_signal(response, default_signal), parse_confidence(response, default_confidence)
