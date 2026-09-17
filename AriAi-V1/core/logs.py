"""
core/logs.py
Persists command history to logs.json in the project root, so the
"COMMAND HISTORY LOGS" panel survives app restarts.
"""
from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime
from pathlib import Path

LOGS_PATH = Path(__file__).resolve().parent.parent / "logs.json"
SUMMARY_PATH = Path(__file__).resolve().parent.parent / "chat_summary.md"
MAX_LOGS = 200


def _timestamped_summary_path() -> Path:
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return Path(__file__).resolve().parent.parent / f"chat_summary_{stamp}.md"

_lock = threading.Lock()

_INIT_LOG = {
    "id": "log-init",
    "timestamp": "",
    "command": "System Ignition Sequence Complete",
    "spoken_text": "All subroutines loaded, sir. Ari mainframe is online.",
    "markdown_text": (
        "### Ari Sub-System AriAI Prime Active\n\n"
        "Welcome back, sir.\n\n"
        "Type a command or press the holographic microphone to dictate tasks or search parameters."
    ),
    "google_search_performed": False,
    "grounding_sources": [],
    "actions_executed": [],
}


def _read() -> list[dict]:
    if not LOGS_PATH.exists():
        return [_INIT_LOG]
    try:
        with open(LOGS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else [_INIT_LOG]
    except (json.JSONDecodeError, OSError):
        return [_INIT_LOG]


def _write(logs: list[dict]) -> None:
    with open(LOGS_PATH, "w", encoding="utf-8") as f:
        json.dump(logs[-MAX_LOGS:], f, indent=2)


def get_logs() -> list[dict]:
    with _lock:
        return _read()


def _build_summary(logs: list[dict]) -> str:
    entries = []
    for item in logs:
        if not isinstance(item, dict):
            continue
        command = (item.get("command") or "").strip()
        if not command or command == _INIT_LOG.get("command"):
            continue
        entries.append({
            "command": command,
            "timestamp": item.get("timestamp", ""),
            "spoken": (item.get("spoken_text") or "").strip(),
            "markdown": (item.get("markdown_text") or "").strip(),
            "search": bool(item.get("google_search_performed")),
        })

    session_title = "# Session Summary"
    if not entries:
        return (
            f"{session_title}\n\n"
            "No command history was captured in this session.\n"
        )

    lines = [
        session_title,
        "",
        f"This session included {len(entries)} command(s).",
        "",
    ]

    for index, entry in enumerate(entries, start=1):
        ts = entry["timestamp"]
        command = entry["command"]
        search_note = " [web search used]" if entry["search"] else ""
        lines.append(f"## {index}. {command} ({ts}){search_note}")
        summary_text = entry["markdown"] or entry["spoken"] or "No details captured."
        lines.append(summary_text)
        lines.append("")

    return "\n".join(lines).strip() + "\n"


def save_chat_snapshot() -> str:
    """Persist the current log and create a plain-text markdown summary."""
    with _lock:
        logs = _read()
        _write(logs)
        summary = _build_summary(logs)

        archive_path = _timestamped_summary_path()
        with open(archive_path, "w", encoding="utf-8") as f:
            f.write(summary)

        with open(SUMMARY_PATH, "w", encoding="utf-8") as f:
            f.write(summary)
        return summary


def clear_logs() -> list[dict]:
    with _lock:
        _write([_INIT_LOG])
        try:
            with open(SUMMARY_PATH, "w", encoding="utf-8") as f:
                f.write("# Session Summary\n\nNo command history was captured in this session.\n")
        except OSError:
            pass
        return [_INIT_LOG]


def add_log(command: str, result: dict) -> list[dict]:
    with _lock:
        logs = _read()
        logs.append(
            {
                "id": str(uuid.uuid4()),
                "timestamp": datetime.now().strftime("%H:%M:%S"),
                "command": command,
                "spoken_text": result.get("spokenText", ""),
                "markdown_text": result.get("markdownText", ""),
                "google_search_performed": result.get("searchPerformed", False),
                "grounding_sources": result.get("groundingSources", []),
                "actions_executed": result.get("actionsExecuted", []),
            }
        )
        _write(logs)
        return logs
