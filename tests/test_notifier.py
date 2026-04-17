from core import notifier


async def test_send_telegram_without_config_returns_false(monkeypatch):
    from config.settings import settings

    monkeypatch.setattr(settings, "telegram_bot_token", "")
    monkeypatch.setattr(settings, "telegram_chat_id", "")

    result = await notifier.send_telegram("test")
    assert result is False


async def test_notify_trade_formats_message(monkeypatch):
    captured: list[str] = []

    async def mock_send(text: str, parse_mode: str = "Markdown") -> bool:
        captured.append(text)
        return True

    monkeypatch.setattr(notifier, "send_telegram", mock_send)

    await notifier.notify_trade("AAPL", "buy", 10, 150.0, 145.0, 165.0, 0.75, "strong signal")

    assert len(captured) == 1
    msg = captured[0]
    assert "BUY AAPL" in msg
    assert "150.00" in msg
    assert "145.00" in msg
    assert "165.00" in msg
    assert "75%" in msg


async def test_notify_cycle_summary(monkeypatch):
    captured: list[str] = []

    async def mock_send(text: str, parse_mode: str = "Markdown") -> bool:
        captured.append(text)
        return True

    monkeypatch.setattr(notifier, "send_telegram", mock_send)

    await notifier.notify_cycle_summary("abc123", 40, 5, 2, 0, 120.5)

    assert len(captured) == 1
    assert "abc123" in captured[0]
    assert "40" in captured[0]
