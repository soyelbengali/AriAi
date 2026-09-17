from pathlib import Path

from core import logs


def test_save_chat_snapshot_writes_summary_and_chat(tmp_path, monkeypatch):
    logs_path = tmp_path / "logs.json"
    summary_path = tmp_path / "chat_summary.md"

    monkeypatch.setattr(logs, "LOGS_PATH", logs_path)
    monkeypatch.setattr(logs, "SUMMARY_PATH", summary_path)

    sample_logs = [
        {
            "id": "1",
            "timestamp": "10:00:00",
            "command": "What is the weather?",
            "spoken_text": "The weather is sunny.",
            "markdown_text": "### Result\nThe weather is sunny and 22C.",
            "google_search_performed": False,
            "grounding_sources": [],
            "actions_executed": [],
        },
        {
            "id": "2",
            "timestamp": "10:02:00",
            "command": "Summarize the launch plan.",
            "spoken_text": "Here is the launch plan.",
            "markdown_text": "### Plan\nShip on Friday and announce in the morning.",
            "google_search_performed": True,
            "grounding_sources": [{"title": "Launch plan"}],
            "actions_executed": ["web_search"],
        },
    ]

    monkeypatch.setattr(logs, "_read", lambda: sample_logs)
    monkeypatch.setattr(logs, "_timestamped_summary_path", lambda: tmp_path / "chat_summary_2026-08-14_10-00-00.md")

    result = logs.save_chat_snapshot()

    assert logs_path.exists()
    assert summary_path.exists()
    assert (tmp_path / "chat_summary_2026-08-14_10-00-00.md").exists()
    assert "Session Summary" in result
    assert "What is the weather?" in result
    assert "2 commands" in result
    assert "Launch plan" in summary_path.read_text(encoding="utf-8")
