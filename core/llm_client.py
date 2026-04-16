from __future__ import annotations
import httpx
import orjson
import hashlib
from cachetools import TTLCache
from config.settings import settings

_cache = TTLCache(maxsize=256, ttl=900)


async def query(prompt: str, system: str = "", temperature: float = 0.3, max_tokens: int = 512) -> str:
    cache_key = hashlib.md5(f"{system}:{prompt}".encode()).hexdigest()
    if cache_key in _cache:
        return _cache[cache_key]

    messages = []
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

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(f"{settings.ollama_base_url}/api/chat", content=orjson.dumps(payload))
            resp.raise_for_status()
            result = orjson.loads(resp.content)
            msg = result.get("message", {})
            text = msg.get("content", "").strip()
            _cache[cache_key] = text
            return text
    except Exception as e:
        return f"[LLM_ERROR] {e}"


async def health_check() -> bool:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{settings.ollama_base_url}/api/tags")
            models = orjson.loads(resp.content).get("models", [])
            return any(settings.ollama_model in m.get("name", "") for m in models)
    except Exception:
        return False
