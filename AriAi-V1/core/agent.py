"""
core/agent.py
Ties the LLM together with the web search tool. The model is given a
`web_search` function it can call (standard OpenAI tool-calling format);
if it calls it, we run core/search.py, feed the results back, and ask for
a final answer. Everything is driven by core/config.py settings.
"""
from __future__ import annotations

import json
from typing import Any

from . import llm_client, search as search_mod

SYSTEM_PROMPT = (
    "You are Ari, a sharp, efficient AI assistant embedded in a desktop HUD "
    "called AriAI System Prime. Address the user as 'sir'. Keep responses "
    "concise and well-structured in Markdown. When you use the web_search "
    "tool, ground your answer in what it returns and do not invent facts."
)

WEB_SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": "Search the live web for current information. Use it for anything time-sensitive, factual-but-uncertain, or post-dating your knowledge.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "A concise search query."}
            },
            "required": ["query"],
        },
    },
}


def _first_choice_message(resp: dict) -> dict:
    choices = resp.get("choices") or []
    if not choices:
        raise RuntimeError("LLM response contained no choices.")
    return choices[0]["message"]


def run(command: str, cfg: dict) -> dict:
    """Runs one command through the agent. Returns a payload matching what
    the frontend (ariai.js: window.onAriResult) expects."""
    llm_cfg = cfg.get("llm", {})
    search_cfg = cfg.get("search", {})
    allow_search = search_cfg.get("enabled", True)

    messages: list[dict] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": command},
    ]

    tools = [WEB_SEARCH_TOOL] if allow_search else None
    grounding_sources: list[dict] = []
    search_performed = False

    resp = llm_client.chat_completion(
        messages=messages,
        base_url=llm_cfg.get("base_url", ""),
        api_key=llm_cfg.get("api_key", ""),
        model=llm_cfg.get("model", ""),
        tools=tools,
    )
    message = _first_choice_message(resp)

    # Tool-calling loop (single round is enough for a search-augmented answer;
    # loop defensively in case the model chains multiple searches).
    hops = 0
    while message.get("tool_calls") and hops < 3:
        hops += 1
        messages.append(message)
        for call in message["tool_calls"]:
            fn = call.get("function", {})
            if fn.get("name") != "web_search":
                continue
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            query = args.get("query", command)

            result = search_mod.web_search(
                query,
                ollama_api_key=search_cfg.get("ollama_api_key", ""),
                parallel_api_key=search_cfg.get("parallel_api_key", ""),
                max_results=search_cfg.get("max_results", 5),
            )
            search_performed = True
            for r in result.get("results", []):
                grounding_sources.append(r)

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.get("id", ""),
                    "content": json.dumps(result.get("results", []))[:6000],
                }
            )

        resp = llm_client.chat_completion(
            messages=messages,
            base_url=llm_cfg.get("base_url", ""),
            api_key=llm_cfg.get("api_key", ""),
            model=llm_cfg.get("model", ""),
            tools=tools,
        )
        message = _first_choice_message(resp)

    markdown_text = message.get("content") or "*(No response content returned.)*"
    spoken_text = _to_spoken(markdown_text)

    return {
        "markdownText": markdown_text,
        "spokenText": spoken_text,
        "searchPerformed": search_performed,
        "groundingSources": grounding_sources,
        "actionsExecuted": [],
    }


def _to_spoken(md: str) -> str:
    """Strip Markdown syntax down to something reasonable to pass to TTS."""
    import re

    text = re.sub(r"```.*?```", "", md, flags=re.S)
    text = re.sub(r"[#*_`>-]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:2000]
