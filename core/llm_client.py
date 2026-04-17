from __future__ import annotations

import asyncio
import hashlib

import httpx
import orjson
from cachetools import TTLCache

from config.settings import settings

_cache: TTLCache = TTLCache(maxsize=512, ttl=900)
_semaphore = asyncio.Semaphore(2)


async def query(
    prompt: str,
    system: str = "",
    temperature: float = 0.3,
    max_tokens: int = 512,
) -> str:
    cache_key = hashlib.md5(f"{system}:{prompt}:{temperature}".encode()).hexdigest()
    if cache_key in _cache:
        return _cache[cache_key]

    messages: list[dict] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": settings.ollama_model,
        "messages": messages,
        "stream": False,
        "think": False,
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens,
        },
    }

    async with _semaphore:
        try:
            async with httpx.AsyncClient(timeout=180.0) as client:
                resp = await client.post(
                    f"{settings.ollama_base_url}/api/chat",
                    content=orjson.dumps(payload),
                )
                resp.raise_for_status()
                result = orjson.loads(resp.content)
                text = result.get("message", {}).get("content", "").strip()
                _cache[cache_key] = text
                return text
        except Exception as e:
            return f"[LLM_ERROR] {e}"


async def query_many(
    prompts: list[tuple[str, str]],
    temperature: float = 0.3,
    max_tokens: int = 512,
) -> list[str]:
    tasks = [query(p, system=s, temperature=temperature, max_tokens=max_tokens) for p, s in prompts]
    return await asyncio.gather(*tasks)


async def health_check() -> bool:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{settings.ollama_base_url}/api/tags")
            models = orjson.loads(resp.content).get("models", [])
            return any(settings.ollama_model in m.get("name", "") for m in models)
    except Exception:
        return False
