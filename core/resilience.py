from __future__ import annotations

import functools
from collections.abc import Awaitable, Callable
from typing import Any

from core.state import PipelineState


def safe_node(agent_name: str) -> Callable:
    def decorator(fn: Callable[[PipelineState], Awaitable[PipelineState]]) -> Callable:
        @functools.wraps(fn)
        async def wrapper(state: PipelineState) -> PipelineState:
            try:
                return await fn(state)
            except Exception as e:
                state.add_error(f"{agent_name}: {type(e).__name__}: {e}")
                return state

        return wrapper

    return decorator


def with_fallback(default_return: Any):
    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            try:
                return await fn(*args, **kwargs)
            except Exception:
                return default_return

        return wrapper

    return decorator
