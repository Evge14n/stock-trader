import pytest

from core.resilience import safe_node, with_fallback
from core.state import PipelineState


@pytest.fixture
def empty_state():
    return PipelineState()


async def test_safe_node_catches_exception(empty_state):
    @safe_node("test_agent")
    async def failing_agent(state: PipelineState) -> PipelineState:
        raise ValueError("boom")

    result = await failing_agent(empty_state)
    assert result is empty_state
    assert any("test_agent" in e for e in result.errors)


async def test_safe_node_passes_through_on_success(empty_state):
    @safe_node("test_agent")
    async def good_agent(state: PipelineState) -> PipelineState:
        state.symbols.append("AAPL")
        return state

    result = await good_agent(empty_state)
    assert result.symbols == ["AAPL"]
    assert result.errors == []


async def test_with_fallback_returns_default_on_error():
    @with_fallback(default_return={"ok": False})
    async def failing() -> dict:
        raise RuntimeError("fail")

    result = await failing()
    assert result == {"ok": False}


async def test_with_fallback_returns_value_on_success():
    @with_fallback(default_return=None)
    async def good() -> str:
        return "hello"

    assert await good() == "hello"
