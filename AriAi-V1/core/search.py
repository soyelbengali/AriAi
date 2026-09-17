"""
core/search.py
Web grounding. Ollama Web Search is the primary provider (fast, cheap,
key-scoped to ollama.com). If it errors, is unreachable, or returns nothing,
we fall back to Parallel's Search API.

Both providers are normalized to the same shape:
    [{ "title": str, "uri": str, "snippet": str }, ...]
so the rest of the app (and the JS "grounding sources" UI) never needs to
know which one actually answered.
"""
from __future__ import annotations

import requests

REQUEST_TIMEOUT = 20

OLLAMA_SEARCH_URL = "https://ollama.com/api/web_search"
PARALLEL_SEARCH_URL = "https://api.parallel.ai/v1/search"


class SearchError(Exception):
    pass


def _normalize_ollama(results: list[dict]) -> list[dict]:
    return [
        {"title": r.get("title") or r.get("url", "Source"), "uri": r.get("url", ""), "snippet": r.get("content", "")}
        for r in results
    ]


def _normalize_parallel(results: list[dict]) -> list[dict]:
    out = []
    for r in results:
        excerpts = r.get("excerpts") or []
        snippet = " ".join(excerpts) if isinstance(excerpts, list) else str(excerpts)
        out.append({"title": r.get("title") or r.get("url", "Source"), "uri": r.get("url", ""), "snippet": snippet})
    return out


def _search_ollama(query: str, api_key: str, max_results: int = 5) -> list[dict]:
    if not api_key:
        raise SearchError("No Ollama Web Search API key configured.")
    resp = requests.post(
        OLLAMA_SEARCH_URL,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"query": query, "max_results": max_results},
        timeout=REQUEST_TIMEOUT,
    )
    if not resp.ok:
        raise SearchError(f"Ollama web_search failed ({resp.status_code}): {resp.text[:200]}")
    data = resp.json()
    return _normalize_ollama(data.get("results", []))


def _search_parallel(query: str, api_key: str, max_results: int = 5) -> list[dict]:
    if not api_key:
        raise SearchError("No Parallel Search API key configured.")
    resp = requests.post(
        PARALLEL_SEARCH_URL,
        headers={"x-api-key": api_key, "Content-Type": "application/json"},
        json={"objective": query, "search_queries": [query], "max_results": max_results},
        timeout=REQUEST_TIMEOUT,
    )
    if not resp.ok:
        raise SearchError(f"Parallel search failed ({resp.status_code}): {resp.text[:200]}")
    data = resp.json()
    return _normalize_parallel(data.get("results", []))[:max_results]


def web_search(query: str, ollama_api_key: str, parallel_api_key: str, max_results: int = 5) -> dict:
    """Tries Ollama Web Search first, falls back to Parallel on any failure
    or empty result set. Returns {"provider": str, "results": [...]}"""
    try:
        results = _search_ollama(query, ollama_api_key, max_results)
        if results:
            return {"provider": "ollama", "results": results}
    except SearchError:
        pass

    try:
        results = _search_parallel(query, parallel_api_key, max_results)
        return {"provider": "parallel", "results": results}
    except SearchError as exc:
        return {"provider": None, "results": [], "error": str(exc)}
