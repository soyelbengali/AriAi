"""
core/config.py
Loads and persists backend configuration to config.json in the project root.
This is the single source of truth for API keys, base URLs and model names
used by the LLM, embeddings, TTS and search modules.

Nothing here is exposed directly to the browser except through main.py's
Api.get_settings()/save_settings(), which strip secrets as needed.
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.json"

DEFAULT_CONFIG: dict[str, Any] = {
    # OpenAI-compatible chat completions server (LM Studio, vLLM, OpenRouter, etc.)
    "llm": {
        "base_url": "https://api.openai.com/v1",
        "api_key": "",
        "model": "gpt-4o-mini",
    },
    # Can point at the same or a different OpenAI-compatible server.
    "embeddings": {
        "base_url": "https://api.openai.com/v1",
        "api_key": "",
        "model": "text-embedding-3-small",
    },
    # Local, CPU-only speech-to-text.
    "stt": {
        "model": "nvidia/canary-180m-flash",
        "device": "cpu",
        "record_seconds": 6,
        "samplerate": 16000,
    },
    # FreeTTS (https://freetts.org) — no API key required.
    "tts": {
        "provider": "puter",
        "voice": "Joanna",
        "piper_model": "en_US-lessac-medium",
    },
    # Web search: Ollama Web Search primary, Parallel Search API fallback.
    "search": {
        "enabled": True,
        "ollama_api_key": "",
        "parallel_api_key": "",
        "max_results": 5,
    },
    "voice_output_enabled": True,
    "voice_input_enabled": True,
    # After Ari finishes speaking, keep the mic open for a short follow-up
    # window so a back-and-forth feels like a real conversation.
    "conversation": {
        "enabled": True,
        "window_seconds": 5,
    },
}

# load_config() creates the initial file by calling save_config().  An RLock is
# required here so first-run setup does not deadlock the UI bridge.
_lock = threading.RLock()


def _deep_merge(base: dict, override: dict) -> dict:
    """Merge override into base, recursing into nested dicts."""
    out = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config() -> dict:
    with _lock:
        if not CONFIG_PATH.exists():
            save_config(DEFAULT_CONFIG)
            return json.loads(json.dumps(DEFAULT_CONFIG))
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            data = {}
        return _deep_merge(DEFAULT_CONFIG, data)


def save_config(data: dict) -> dict:
    with _lock:
        current = {}
        if CONFIG_PATH.exists():
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    current = json.load(f)
            except (json.JSONDecodeError, OSError):
                current = {}
        merged = _deep_merge(_deep_merge(DEFAULT_CONFIG, current), data)
        # Do not leave a partially-written config if the process exits mid-save.
        temp_path = CONFIG_PATH.with_suffix(".json.tmp")
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(merged, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_path, CONFIG_PATH)
        return merged
