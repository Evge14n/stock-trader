import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest


@pytest.fixture(autouse=True)
def isolated_db(monkeypatch, tmp_path):
    from agents.python import paper_broker

    test_db = tmp_path / "test_broker.db"
    monkeypatch.setattr(paper_broker, "_db_path", lambda: test_db)
    yield test_db


@pytest.fixture
def sample_ohlcv():
    import math

    candles = []
    base_price = 150.0
    for i in range(60):
        drift = math.sin(i / 10) * 5
        price = base_price + drift + (i * 0.3)
        candles.append({
            "timestamp": 1700000000 + i * 86400,
            "open": price - 1,
            "high": price + 2,
            "low": price - 2,
            "close": price,
            "volume": 1_000_000 + i * 10_000,
        })
    return candles
