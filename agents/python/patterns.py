from __future__ import annotations

import pandas as pd

from core.state import Analysis, PipelineState


def _find_local_extrema(prices: pd.Series, window: int = 3) -> tuple[list[int], list[int]]:
    peaks: list[int] = []
    troughs: list[int] = []

    for i in range(window, len(prices) - window):
        local = prices.iloc[i - window : i + window + 1]
        center = prices.iloc[i]
        if center == local.max() and center > prices.iloc[i - 1]:
            peaks.append(i)
        elif center == local.min() and center < prices.iloc[i - 1]:
            troughs.append(i)

    return peaks, troughs


def detect_double_top(prices: pd.Series, peaks: list[int], tolerance: float = 0.02) -> dict | None:
    if len(peaks) < 2:
        return None

    last_two = peaks[-2:]
    p1, p2 = prices.iloc[last_two[0]], prices.iloc[last_two[1]]
    if abs(p1 - p2) / max(p1, p2) > tolerance:
        return None

    if last_two[1] < len(prices) - 1:
        between_min = prices.iloc[last_two[0] : last_two[1]].min()
        depth = (max(p1, p2) - between_min) / max(p1, p2)
        if depth < 0.03:
            return None
        return {"pattern": "double_top", "signal": "bearish", "confidence": 0.7, "strength": round(depth, 3)}

    return None


def detect_double_bottom(prices: pd.Series, troughs: list[int], tolerance: float = 0.02) -> dict | None:
    if len(troughs) < 2:
        return None

    last_two = troughs[-2:]
    p1, p2 = prices.iloc[last_two[0]], prices.iloc[last_two[1]]
    if abs(p1 - p2) / max(p1, p2) > tolerance:
        return None

    between_max = prices.iloc[last_two[0] : last_two[1]].max()
    depth = (between_max - min(p1, p2)) / between_max
    if depth < 0.03:
        return None

    return {"pattern": "double_bottom", "signal": "bullish", "confidence": 0.7, "strength": round(depth, 3)}


def detect_head_and_shoulders(prices: pd.Series, peaks: list[int]) -> dict | None:
    if len(peaks) < 3:
        return None

    left, head, right = peaks[-3], peaks[-2], peaks[-1]
    left_p, head_p, right_p = prices.iloc[left], prices.iloc[head], prices.iloc[right]

    if head_p <= left_p or head_p <= right_p:
        return None

    shoulders_similar = abs(left_p - right_p) / max(left_p, right_p) < 0.04
    head_higher = (head_p - max(left_p, right_p)) / head_p > 0.02

    if shoulders_similar and head_higher:
        return {
            "pattern": "head_and_shoulders",
            "signal": "bearish",
            "confidence": 0.75,
            "strength": round(head_higher, 3),
        }

    return None


def detect_cup_and_handle(prices: pd.Series) -> dict | None:
    if len(prices) < 50:
        return None

    recent = prices.iloc[-50:]
    mid = len(recent) // 2
    cup_low = recent.iloc[10 : mid + 10].min()
    cup_start = recent.iloc[0]
    cup_end = recent.iloc[mid + 10]

    cup_depth = (cup_start - cup_low) / cup_start if cup_start else 0
    cup_recovery = abs(cup_end - cup_start) / cup_start if cup_start else 0

    if cup_depth > 0.05 and cup_recovery < 0.03:
        handle = recent.iloc[mid + 10 :]
        handle_low = handle.min()
        handle_recovery = (recent.iloc[-1] - handle_low) / handle_low if handle_low else 0
        if 0.01 < handle_recovery < 0.05:
            return {
                "pattern": "cup_and_handle",
                "signal": "bullish",
                "confidence": 0.8,
                "strength": round(cup_depth, 3),
            }

    return None


def detect_triangle(prices: pd.Series, peaks: list[int], troughs: list[int]) -> dict | None:
    if len(peaks) < 2 or len(troughs) < 2:
        return None

    recent_peaks = peaks[-3:] if len(peaks) >= 3 else peaks
    recent_troughs = troughs[-3:] if len(troughs) >= 3 else troughs

    peak_vals = [prices.iloc[p] for p in recent_peaks]
    trough_vals = [prices.iloc[t] for t in recent_troughs]

    if len(peak_vals) >= 2 and len(trough_vals) >= 2:
        peaks_falling = peak_vals[-1] < peak_vals[0] * 0.98
        troughs_rising = trough_vals[-1] > trough_vals[0] * 1.02

        if peaks_falling and troughs_rising:
            return {"pattern": "symmetric_triangle", "signal": "neutral", "confidence": 0.6, "strength": 0.5}
        if peaks_falling and not troughs_rising:
            return {"pattern": "descending_triangle", "signal": "bearish", "confidence": 0.65, "strength": 0.5}
        if not peaks_falling and troughs_rising:
            return {"pattern": "ascending_triangle", "signal": "bullish", "confidence": 0.65, "strength": 0.5}

    return None


def detect_patterns(candles: list[dict]) -> list[dict]:
    if len(candles) < 20:
        return []

    df = pd.DataFrame(candles).sort_values("timestamp").reset_index(drop=True)
    closes = df["close"]

    peaks, troughs = _find_local_extrema(closes, window=3)
    patterns = []

    for detector in [
        lambda: detect_double_top(closes, peaks),
        lambda: detect_double_bottom(closes, troughs),
        lambda: detect_head_and_shoulders(closes, peaks),
        lambda: detect_cup_and_handle(closes),
        lambda: detect_triangle(closes, peaks, troughs),
    ]:
        result = detector()
        if result:
            patterns.append(result)

    return patterns


async def analyze(state: PipelineState) -> PipelineState:
    for symbol in state.symbols:
        md = state.market_data.get(symbol)
        if not md or not md.ohlcv:
            continue

        patterns = detect_patterns(md.ohlcv)
        if not patterns:
            continue

        bullish = sum(1 for p in patterns if p["signal"] == "bullish")
        bearish = sum(1 for p in patterns if p["signal"] == "bearish")

        if bullish > bearish:
            signal = "bullish"
        elif bearish > bullish:
            signal = "bearish"
        else:
            signal = "neutral"

        avg_conf = sum(p["confidence"] for p in patterns) / len(patterns)
        pattern_names = ", ".join(p["pattern"] for p in patterns)

        state.analyses.setdefault(symbol, []).append(
            Analysis(
                agent="pattern_recognizer",
                symbol=symbol,
                signal=signal,
                confidence=round(avg_conf, 3),
                reasoning=f"Detected: {pattern_names}",
            )
        )

    return state
