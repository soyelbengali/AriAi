"""
core/llm_client.py
Thin wrapper around any OpenAI-compatible /v1 server (OpenAI, OpenRouter,
LM Studio, vLLM, llama.cpp server, Ollama's OpenAI-compat endpoint, etc.)
for both chat completions and embeddings. Base URL, API key and model are
all user-configurable (see core/config.py -> "llm" / "embeddings").
"""
from __future__ import annotations

from typing import Any, Optional

import requests

REQUEST_TIMEOUT = 60


class LLMError(Exception):
    pass


def _headers(api_key: str) -> dict:
    h = {"Content-Type": "application/json"}
    if api_key:
        h["Authorization"] = f"Bearer {api_key}"
    return h


def chat_completion(
    messages: list[dict],
    base_url: str,
    api_key: str,
    model: str,
    tools: Optional[list[dict]] = None,
    temperature: float = 0.4,
    max_tokens: int = 1200,
) -> dict:
    """Calls POST {base_url}/chat/completions. Returns the parsed response body."""
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    resp = requests.post(
        f"{base_url.rstrip('/')}/chat/completions",
        headers=_headers(api_key),
        json=payload,
        timeout=REQUEST_TIMEOUT,
    )
    if not resp.ok:
        raise LLMError(f"LLM chat/completions failed ({resp.status_code}): {resp.text[:300]}")
    return resp.json()


def embed(
    texts: list[str],
    base_url: str,
    api_key: str,
    model: str,
) -> list[list[float]]:
    """Calls POST {base_url}/embeddings. Returns a list of embedding vectors,
    in the same order as `texts`."""
    resp = requests.post(
        f"{base_url.rstrip('/')}/embeddings",
        headers=_headers(api_key),
        json={"model": model, "input": texts},
        timeout=REQUEST_TIMEOUT,
    )
    if not resp.ok:
        raise LLMError(f"LLM embeddings failed ({resp.status_code}): {resp.text[:300]}")
    data = resp.json()
    items = sorted(data.get("data", []), key=lambda d: d.get("index", 0))
    return [item["embedding"] for item in items]


def list_models(base_url: str, api_key: str) -> list[str]:
    """Calls GET {base_url}/models. Used to populate a model picker in the UI."""
    resp = requests.get(
        f"{base_url.rstrip('/')}/models",
        headers=_headers(api_key),
        timeout=REQUEST_TIMEOUT,
    )
    if not resp.ok:
        raise LLMError(f"LLM /models failed ({resp.status_code}): {resp.text[:300]}")
    data = resp.json()
    return [m.get("id") for m in data.get("data", []) if m.get("id")]
