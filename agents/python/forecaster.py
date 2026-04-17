from __future__ import annotations

from pathlib import Path

import numpy as np
import orjson

from agents.python.data_collector import fetch_candles
from config.settings import settings


def _build_features(
    closes: np.ndarray, volumes: np.ndarray, highs: np.ndarray, lows: np.ndarray, lookback: int = 20
) -> tuple[np.ndarray, np.ndarray]:
    X, y = [], []
    for i in range(lookback, len(closes) - 1):
        window_close = closes[i - lookback : i]
        window_vol = volumes[i - lookback : i]

        returns = np.diff(window_close) / window_close[:-1]

        features = [
            (closes[i] - window_close.mean()) / window_close.std() if window_close.std() else 0,
            returns.mean() if len(returns) else 0,
            returns.std() if len(returns) else 0,
            (closes[i] - window_close.min()) / (window_close.max() - window_close.min())
            if window_close.max() > window_close.min()
            else 0.5,
            (volumes[i] - window_vol.mean()) / window_vol.std() if window_vol.std() else 0,
            (highs[i] - lows[i]) / closes[i] if closes[i] else 0,
            closes[i] / window_close[-5:].mean() - 1 if len(window_close) >= 5 else 0,
        ]

        target_return = (closes[i + 1] - closes[i]) / closes[i]
        X.append(features)
        y.append(target_return)

    return np.array(X), np.array(y)


def _model_path(symbol: str) -> Path:
    d = settings.data_dir / "forecaster_models"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{symbol}_model.json"


def train_forecaster(symbol: str, period: str = "1y") -> dict:
    from sklearn.neural_network import MLPRegressor
    from sklearn.preprocessing import StandardScaler

    candles = fetch_candles(symbol, period=period)
    if len(candles) < 50:
        return {"error": "insufficient data", "symbol": symbol}

    closes = np.array([c["close"] for c in candles])
    volumes = np.array([c["volume"] for c in candles])
    highs = np.array([c["high"] for c in candles])
    lows = np.array([c["low"] for c in candles])

    X, y = _build_features(closes, volumes, highs, lows)
    if len(X) < 30:
        return {"error": "insufficient features", "symbol": symbol}

    split = int(len(X) * 0.8)
    X_train, X_test = X[:split], X[split:]
    y_train, y_test = y[:split], y[split:]

    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_test_s = scaler.transform(X_test)

    model = MLPRegressor(
        hidden_layer_sizes=(16, 8),
        max_iter=500,
        learning_rate_init=0.01,
        random_state=42,
        early_stopping=True,
        validation_fraction=0.15,
    )
    model.fit(X_train_s, y_train)

    train_score = float(model.score(X_train_s, y_train))
    test_score = float(model.score(X_test_s, y_test)) if len(X_test_s) else 0

    predictions = model.predict(X_test_s)
    sign_match = sum(1 for p, a in zip(predictions, y_test, strict=False) if (p > 0) == (a > 0))
    directional_accuracy = sign_match / len(predictions) if len(predictions) else 0

    model_data = {
        "symbol": symbol,
        "hidden_layers": [16, 8],
        "coefs": [c.tolist() for c in model.coefs_],
        "intercepts": [i.tolist() for i in model.intercepts_],
        "scaler_mean": scaler.mean_.tolist(),
        "scaler_std": scaler.scale_.tolist(),
        "train_r2": train_score,
        "test_r2": test_score,
        "directional_accuracy": directional_accuracy,
        "samples": len(X),
    }

    _model_path(symbol).write_bytes(orjson.dumps(model_data, option=orjson.OPT_INDENT_2))

    return {
        "symbol": symbol,
        "train_r2": round(train_score, 3),
        "test_r2": round(test_score, 3),
        "directional_accuracy": round(directional_accuracy * 100, 1),
        "samples": len(X),
        "model_saved": True,
    }


def _apply_mlp(features: np.ndarray, model_data: dict) -> float:
    scaler_mean = np.array(model_data["scaler_mean"])
    scaler_std = np.array(model_data["scaler_std"])
    scaler_std = np.where(scaler_std == 0, 1, scaler_std)
    x = (features - scaler_mean) / scaler_std

    for coefs, intercepts in zip(model_data["coefs"][:-1], model_data["intercepts"][:-1], strict=False):
        x = x @ np.array(coefs) + np.array(intercepts)
        x = np.maximum(0, x)

    x = x @ np.array(model_data["coefs"][-1]) + np.array(model_data["intercepts"][-1])
    return float(x.item() if hasattr(x, "item") else x[0])


def predict_next_return(symbol: str) -> dict:
    path = _model_path(symbol)
    if not path.exists():
        return {"error": "model not trained", "symbol": symbol}

    try:
        model_data = orjson.loads(path.read_bytes())
    except Exception as e:
        return {"error": f"model load failed: {e}", "symbol": symbol}

    candles = fetch_candles(symbol, period="2mo")
    if len(candles) < 25:
        return {"error": "insufficient recent data", "symbol": symbol}

    closes = np.array([c["close"] for c in candles])
    volumes = np.array([c["volume"] for c in candles])
    highs = np.array([c["high"] for c in candles])
    lows = np.array([c["low"] for c in candles])

    lookback = 20
    window_close = closes[-lookback:]
    window_vol = volumes[-lookback:]
    returns = np.diff(window_close) / window_close[:-1]

    features = np.array(
        [
            (closes[-1] - window_close.mean()) / window_close.std() if window_close.std() else 0,
            returns.mean() if len(returns) else 0,
            returns.std() if len(returns) else 0,
            (closes[-1] - window_close.min()) / (window_close.max() - window_close.min())
            if window_close.max() > window_close.min()
            else 0.5,
            (volumes[-1] - window_vol.mean()) / window_vol.std() if window_vol.std() else 0,
            (highs[-1] - lows[-1]) / closes[-1] if closes[-1] else 0,
            closes[-1] / window_close[-5:].mean() - 1 if len(window_close) >= 5 else 0,
        ]
    )

    predicted_return = _apply_mlp(features, model_data)
    predicted_price = closes[-1] * (1 + predicted_return)

    signal = "bullish" if predicted_return > 0.01 else "bearish" if predicted_return < -0.01 else "neutral"
    confidence = min(0.85, abs(predicted_return) * 30)

    return {
        "symbol": symbol,
        "current_price": round(float(closes[-1]), 2),
        "predicted_return_pct": round(predicted_return * 100, 2),
        "predicted_next_price": round(predicted_price, 2),
        "signal": signal,
        "confidence": round(confidence, 3),
        "model_accuracy": model_data.get("directional_accuracy", 0),
    }


def train_all_watchlist() -> list[dict]:
    results = []
    for sym in settings.symbols:
        result = train_forecaster(sym)
        results.append(result)
    return results
