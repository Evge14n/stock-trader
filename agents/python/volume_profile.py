from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class VolumeProfile:
    symbol: str = ""
    point_of_control: float = 0.0
    value_area_high: float = 0.0
    value_area_low: float = 0.0
    histogram: list[dict] = field(default_factory=list)
    support_levels: list[float] = field(default_factory=list)
    resistance_levels: list[float] = field(default_factory=list)
    current_price: float = 0.0
    position_relative: str = ""


def calculate_profile(candles: list[dict], bins: int = 30, value_area_pct: float = 0.7) -> VolumeProfile:
    if len(candles) < 20:
        return VolumeProfile()

    highs = np.array([c["high"] for c in candles])
    lows = np.array([c["low"] for c in candles])
    closes = np.array([c["close"] for c in candles])
    volumes = np.array([c["volume"] for c in candles])

    price_min = lows.min()
    price_max = highs.max()
    bin_edges = np.linspace(price_min, price_max, bins + 1)
    bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2

    volume_by_bin = np.zeros(bins)

    for i in range(len(candles)):
        candle_range = highs[i] - lows[i]
        if candle_range == 0:
            continue

        for b in range(bins):
            low = bin_edges[b]
            high = bin_edges[b + 1]
            overlap_low = max(low, lows[i])
            overlap_high = min(high, highs[i])
            if overlap_high > overlap_low:
                overlap_ratio = (overlap_high - overlap_low) / candle_range
                volume_by_bin[b] += volumes[i] * overlap_ratio

    if volume_by_bin.sum() == 0:
        return VolumeProfile()

    poc_idx = int(np.argmax(volume_by_bin))
    poc = float(bin_centers[poc_idx])

    total_volume = volume_by_bin.sum()
    target_volume = total_volume * value_area_pct

    sorted_indices = np.argsort(volume_by_bin)[::-1]
    cumulative = 0
    value_area_indices = []
    for idx in sorted_indices:
        cumulative += volume_by_bin[idx]
        value_area_indices.append(int(idx))
        if cumulative >= target_volume:
            break

    va_prices = bin_centers[value_area_indices]
    vah = float(va_prices.max())
    val = float(va_prices.min())

    histogram = [
        {
            "price": round(float(bin_centers[i]), 2),
            "volume": float(volume_by_bin[i]),
            "pct": round(float(volume_by_bin[i] / total_volume * 100), 2),
        }
        for i in range(bins)
    ]

    threshold = np.percentile(volume_by_bin, 80)
    high_volume_nodes = bin_centers[volume_by_bin >= threshold]

    current = float(closes[-1])
    support = sorted([float(p) for p in high_volume_nodes if p < current], reverse=True)[:3]
    resistance = sorted([float(p) for p in high_volume_nodes if p > current])[:3]

    if current < val:
        position = "below_value_area"
    elif current > vah:
        position = "above_value_area"
    else:
        position = "inside_value_area"

    return VolumeProfile(
        point_of_control=round(poc, 2),
        value_area_high=round(vah, 2),
        value_area_low=round(val, 2),
        histogram=histogram,
        support_levels=[round(s, 2) for s in support],
        resistance_levels=[round(r, 2) for r in resistance],
        current_price=round(current, 2),
        position_relative=position,
    )


def interpret_profile(profile: VolumeProfile) -> dict:
    if not profile.point_of_control:
        return {"signal": "neutral", "reasoning": "insufficient data"}

    notes = []
    score = 0

    if profile.position_relative == "below_value_area":
        notes.append(f"Price ${profile.current_price} below value area — potentially oversold")
        score += 1
    elif profile.position_relative == "above_value_area":
        notes.append(f"Price ${profile.current_price} above value area — potentially overbought")
        score -= 1
    else:
        notes.append("Price inside value area — fair value zone")

    if profile.support_levels:
        nearest_support = profile.support_levels[0]
        distance_pct = (profile.current_price - nearest_support) / profile.current_price * 100
        notes.append(f"Nearest support: ${nearest_support} ({distance_pct:.1f}% below)")
        if distance_pct < 2:
            notes.append("Very close to strong support — bounce possibility")
            score += 0.5

    if profile.resistance_levels:
        nearest_resistance = profile.resistance_levels[0]
        distance_pct = (nearest_resistance - profile.current_price) / profile.current_price * 100
        notes.append(f"Nearest resistance: ${nearest_resistance} ({distance_pct:.1f}% above)")
        if distance_pct < 2:
            notes.append("Very close to strong resistance — reversal possibility")
            score -= 0.5

    poc_diff_pct = (profile.current_price - profile.point_of_control) / profile.point_of_control * 100
    if abs(poc_diff_pct) < 1:
        notes.append(f"At Point of Control (${profile.point_of_control}) — market agreement zone")

    signal = "bullish" if score >= 1 else "bearish" if score <= -1 else "neutral"

    return {
        "signal": signal,
        "score": round(score, 2),
        "reasoning": ". ".join(notes),
    }


def analyze_symbol(symbol: str, candles: list[dict]) -> dict:
    profile = calculate_profile(candles)
    profile.symbol = symbol
    interpretation = interpret_profile(profile)

    return {
        "symbol": symbol,
        "point_of_control": profile.point_of_control,
        "value_area_high": profile.value_area_high,
        "value_area_low": profile.value_area_low,
        "current_price": profile.current_price,
        "position": profile.position_relative,
        "support": profile.support_levels,
        "resistance": profile.resistance_levels,
        "signal": interpretation["signal"],
        "reasoning": interpretation["reasoning"],
    }
