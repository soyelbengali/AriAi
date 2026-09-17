"""
main.py
AriAI System Prime — desktop entrypoint.

Boots a pywebview window over gui/ariai.html and exposes an `Api` object
(window.pywebview.api in the JS) that bridges to:
  - core/agent.py    (LLM + tool-calling web search)
  - core/stt.py       (Canary 180M Flash, CPU)
  - core/piper_tts.py (local Piper fallback)
  - core/config.py    (settings persistence)
  - core/logs.py       (command history)

Long-running work (LLM calls, STT, TTS) is dispatched on background threads
so the webview event loop never blocks; results are pushed back into the
page via window.evaluate_js, matching the callbacks ariai.js already
listens for (onAriStatus / onAriResult / onVoiceStatus / onVoiceResult /
onVoiceError).
"""
from __future__ import annotations

import json
import threading
from pathlib import Path

import webview

from core import agent, config, logs, piper_tts, stt

GUI_DIR = Path(__file__).resolve().parent / "gui"
APP_ICON = Path(__file__).resolve().parent / "AriAIlogo.ico"


class Api:
    def __init__(self):
        self._window: webview.Window | None = None

    def set_window(self, window: webview.Window):
        self._window = window

    # ---- helpers -----------------------------------------------------
    def _push(self, fn_name: str, payload=None):
        if not self._window:
            return
        js_payload = "undefined" if payload is None else json.dumps(payload)
        try:
            self._window.evaluate_js(f"window.{fn_name} && window.{fn_name}({js_payload})")
        except Exception as exc:  # noqa: BLE001
            print(f"evaluate_js failed for {fn_name}: {exc}")

    # ---- logs -----------------------------------------------------------
    def get_logs(self):
        return logs.get_logs()

    def clear_logs(self):
        return logs.clear_logs()

    # ---- settings ---------------------------------------------------------
    def get_settings(self):
        return config.load_config()

    def save_settings(self, settings: dict):
        return config.save_config(settings or {})

    # ---- model discovery ----------------------------------------------
    def list_llm_models(self):
        cfg = config.load_config()["llm"]
        from core import llm_client

        try:
            return llm_client.list_models(cfg["base_url"], cfg["api_key"])
        except Exception as exc:  # noqa: BLE001
            print(f"list_llm_models failed: {exc}")
            return []

    def list_embedding_models(self):
        cfg = config.load_config()["embeddings"]
        from core import llm_client

        try:
            return llm_client.list_models(cfg["base_url"], cfg["api_key"])
        except Exception as exc:  # noqa: BLE001
            print(f"list_embedding_models failed: {exc}")
            return []

    # ---- voice availability -------------------------------------------
    def get_voice_availability(self):
        available, reason = stt.is_available()
        return {"available": available, "reason": reason}

    # ---- command execution (text or transcribed voice) -----------------
    def execute_command(self, command: str):
        threading.Thread(target=self._run_command, args=(command,), daemon=True).start()
        return {"queued": True}

    def _run_command(self, command: str):
        self._push("onAriStatus", "thinking")
        cfg = config.load_config()
        try:
            result = agent.run(command, cfg)
        except Exception as exc:  # noqa: BLE001
            self._push("onAriStatus", "error")
            self._push(
                "onAriResult",
                {
                    "markdownText": f"### System Fault\n\nAri hit an error resolving that command:\n\n```\n{exc}\n```",
                    "spokenText": "I apologise, sir. A system error occurred while resolving that command.",
                    "searchPerformed": False,
                    "groundingSources": [],
                    "actionsExecuted": [],
                },
            )
            return

        logs.add_log(command, result)
        self._push("onAriResult", result)

        if cfg.get("voice_output_enabled") and result.get("spokenText"):
            if cfg.get("tts", {}).get("provider", "puter") == "puter":
                self._push("onAriSpeak", result["spokenText"])
            else:
                self._speak(result["spokenText"], cfg)

    # ---- voice input (mic) ---------------------------------------------
    def start_listening(self):
        threading.Thread(target=self._run_listen, daemon=True).start()
        return {"started": True}

    def _run_listen(self):
        cfg = config.load_config()
        self._push("onVoiceStatus", "loading")
        try:
            available, reason = stt.is_available()
            if not available:
                raise RuntimeError(reason)
            self._push("onVoiceStatus", "listening")
            text = stt.record_and_transcribe(
                seconds=cfg["stt"].get("record_seconds", 6),
                samplerate=cfg["stt"].get("samplerate", 16000),
            )
        except Exception as exc:  # noqa: BLE001
            self._push("onVoiceError", str(exc))
            return

        if not text.strip():
            self._push("onVoiceError", "No speech detected, sir.")
            return

        self._push("onVoiceResult", text)

    # ---- voice output (TTS) ---------------------------------------------
    def speak_text(self, text: str):
        cfg = config.load_config()
        if cfg.get("tts", {}).get("provider", "puter") == "puter":
            self._push("onAriSpeak", text)
            return {"ok": True}
        threading.Thread(target=self._speak, args=(text, cfg), daemon=True).start()
        return {"ok": True}

    def _speak(self, text: str, cfg: dict):
        self._push("onAriStatus", "speaking")
        tts_cfg = cfg.get("tts", {})
        try:
            paths = piper_tts.synthesize(
                text,
                model=tts_cfg.get("piper_model", "en_US-lessac-medium"),
            )
            for p in paths:
                _play_audio_blocking(p)
        except Exception as exc:  # noqa: BLE001
            print(f"TTS playback failed: {exc}")
        finally:
            self._push("onAriStatus", "idle")

        self._maybe_open_conversation_window(cfg)

    def _maybe_open_conversation_window(self, cfg: dict):
        """After Ari speaks, keep the mic open for a short follow-up window so
        a back-and-forth feels conversational instead of one command at a time.
        Reuses the same onVoiceResult path a manual mic press uses, so a
        transcribed follow-up flows straight back into execute_command."""
        conv_cfg = cfg.get("conversation", {})
        if not conv_cfg.get("enabled", True) or not cfg.get("voice_input_enabled", True):
            return

        window_seconds = conv_cfg.get("window_seconds", 5)
        self._push("onVoiceStatus", "listening")
        try:
            text = stt.record_and_transcribe(
                seconds=window_seconds,
                samplerate=cfg["stt"].get("samplerate", 16000),
            )
        except Exception as exc:  # noqa: BLE001
            print(f"Conversation follow-up listen failed: {exc}")
            self._push("onVoiceStatus", "idle")
            return

        if not text.strip():
            # Silence — end the conversational loop quietly, no error banner.
            self._push("onVoiceStatus", "idle")
            return

        # Feed the follow-up straight back into the command pipeline. This
        # itself will eventually call _speak() again, which re-opens another
        # follow-up window — the loop naturally ends on silence.
        self._push("onVoiceResult", text)


def _play_audio_blocking(path: str):
    """Best-effort cross-platform audio playback without extra native deps."""
    try:
        from playsound import playsound

        playsound(path)
        return
    except Exception:
        pass

    import platform
    import subprocess

    system = platform.system()
    try:
        if system == "Darwin":
            subprocess.run(["afplay", path], check=False)
        elif system == "Windows":
            import winsound

            winsound.PlaySound(path, winsound.SND_FILENAME)
        else:
            subprocess.run(["ffplay", "-nodisp", "-autoexit", path], check=False,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as exc:  # noqa: BLE001
        print(f"No audio backend could play {path}: {exc}")


def main():
    api = Api()
    window = webview.create_window(
        "AriAI — System Prime",
        str(GUI_DIR / "ariai.html"),
        js_api=api,
        width=1440,
        height=900,
        min_size=(1100, 720),
        background_color="#0a0a0f",
    )
    api.set_window(window)

    def _on_window_closing():
        try:
            logs.save_chat_snapshot()
        except Exception as exc:  # noqa: BLE001
            print(f"Failed to save session summary on close: {exc}")

    window.events.closing += _on_window_closing
    webview.start(debug=False, icon=str(APP_ICON) if APP_ICON.exists() else None)


if __name__ == "__main__":
    main()
