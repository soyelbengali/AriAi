"""Local Piper TTS fallback.

Piper runs entirely on the user's machine.  Its CLI downloads the selected
voice model automatically the first time it is used and writes a WAV file that
the existing desktop playback helper can play.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import threading
from pathlib import Path


class PiperTTSError(Exception):
    """Raised when the local Piper engine cannot synthesize speech."""


_download_lock = threading.Lock()


def _voice_directory() -> Path:
    """Use a stable, user-writable location for downloaded Piper voices."""
    return Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "AriAI" / "piper-voices"


def _ensure_voice(model: str) -> Path:
    voice_dir = _voice_directory()
    voice_file = voice_dir / f"{model}.onnx"
    if voice_file.exists():
        return voice_file

    with _download_lock:
        if voice_file.exists():
            return voice_file
        voice_dir.mkdir(parents=True, exist_ok=True)
        try:
            result = subprocess.run(
                [sys.executable, "-m", "piper.download_voices", model, "--download-dir", str(voice_dir)],
                text=True,
                capture_output=True,
                timeout=300,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise PiperTTSError("Piper timed out while downloading its voice model.") from exc
        if result.returncode != 0 or not voice_file.exists():
            detail = (result.stderr or result.stdout or "Unknown voice download error").strip()
            raise PiperTTSError(f"Piper voice download failed: {detail[:300]}")
    return voice_file


def synthesize(text: str, model: str = "en_US-lessac-medium") -> list[str]:
    """Create a WAV file with Piper and return its path."""
    text = text.strip()
    if not text:
        return []

    voice_file = _ensure_voice(model)
    output = tempfile.NamedTemporaryFile(prefix="ariai_piper_", suffix=".wav", delete=False)
    output_path = Path(output.name)
    output.close()
    try:
        result = subprocess.run(
            ["piper", "-m", str(voice_file), "-f", str(output_path)],
            input=text,
            text=True,
            capture_output=True,
            timeout=120,
            check=False,
        )
    except FileNotFoundError as exc:
        output_path.unlink(missing_ok=True)
        raise PiperTTSError("Piper is not installed. Run: pip install piper-tts") from exc
    except subprocess.TimeoutExpired as exc:
        output_path.unlink(missing_ok=True)
        raise PiperTTSError("Piper timed out while preparing the voice model.") from exc

    if result.returncode != 0 or not output_path.exists() or output_path.stat().st_size == 0:
        output_path.unlink(missing_ok=True)
        detail = (result.stderr or result.stdout or "Unknown Piper error").strip()
        raise PiperTTSError(f"Piper synthesis failed: {detail[:300]}")
    return [str(output_path)]
