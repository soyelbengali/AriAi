"""
core/stt.py
Speech-to-text using NVIDIA Canary 180M Flash, forced onto CPU (laptop-friendly).

Canary-180M-Flash is distributed as a NeMo checkpoint, so we load it through
the `nemo_toolkit[asr]` package. The model is loaded lazily (first use) and
cached for the lifetime of the process, since loading takes a few seconds.

Recording is done with `sounddevice` straight to a temp WAV file, then handed
to the model for transcription.
"""
from __future__ import annotations

import tempfile
import threading
from pathlib import Path
from typing import Optional

_model_lock = threading.Lock()
_model = None
_load_error: Optional[str] = None

MODEL_ID = "nvidia/canary-180m-flash"


def _load_model():
    """Load the Canary model once, pinned to CPU. Raises on failure."""
    global _model, _load_error
    with _model_lock:
        if _model is not None or _load_error is not None:
            return
        try:
            import torch  # noqa: F401
            from nemo.collections.asr.models import EncDecMultiTaskModel

            m = EncDecMultiTaskModel.from_pretrained(MODEL_ID, map_location="cpu")
            m.eval()
            # Force CPU explicitly — this model is small enough to run fast
            # on a laptop CPU and we never want it grabbing a GPU/MPS device
            # if one happens to be present.
            m = m.to("cpu")

            decode_cfg = m.cfg.decoding
            decode_cfg.beam.beam_size = 1
            m.change_decoding_strategy(decode_cfg)

            _model = m
        except Exception as exc:  # noqa: BLE001
            _load_error = f"Failed to load Canary STT model: {exc}"


def is_available() -> tuple[bool, str]:
    """Returns (available, reason). Triggers a lazy load attempt."""
    _load_model()
    if _model is not None:
        return True, "ready"
    return False, _load_error or "unknown STT error"


def _transcribe_compat(wav_path: str, source_lang: str = "en", target_lang: str = "en"):
    """Call Canary transcribe with a compatibility fallback for old/new NeMo APIs."""
    attempts = [
        {
            "source_lang": source_lang,
            "target_lang": target_lang,
            "task": "asr",
            "pnc": "yes",
            "batch_size": 1,
        },
        {
            "source_lang": source_lang,
            "target_lang": target_lang,
            "pnc": "yes",
            "batch_size": 1,
        },
        {
            "pnc": "yes",
            "batch_size": 1,
        },
        {
            "batch_size": 1,
        },
        {},
    ]

    last_error: Exception | None = None
    for kwargs in attempts:
        try:
            return _model.transcribe([wav_path], **kwargs)
        except TypeError as exc:
            message = str(exc)
            if "unexpected keyword argument" not in message.lower() and "positional" not in message.lower():
                raise
            last_error = exc
            continue

    if last_error is not None:
        raise last_error
    raise RuntimeError("Canary STT transcribe failed without producing a result.")


def transcribe_file(wav_path: str, source_lang: str = "en", target_lang: str = "en") -> str:
    """Transcribe a WAV file (16kHz mono recommended) and return plain text."""
    _load_model()
    if _model is None:
        raise RuntimeError(_load_error or "Canary STT model is not available.")

    result = _transcribe_compat(wav_path, source_lang=source_lang, target_lang=target_lang)
    if not result:
        return ""
    item = result[0]
    # NeMo returns either plain strings or Hypothesis objects depending on version.
    text = getattr(item, "text", None)
    return (text if text is not None else str(item)).strip()


def record_and_transcribe(seconds: int = 6, samplerate: int = 16000) -> str:
    """Record `seconds` of mic audio at `samplerate` and transcribe it."""
    import numpy as np
    import sounddevice as sd
    import soundfile as sf

    frames = sd.rec(int(seconds * samplerate), samplerate=samplerate, channels=1, dtype="float32")
    sd.wait()

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        wav_path = tmp.name
    sf.write(wav_path, np.squeeze(frames), samplerate, subtype="PCM_16")

    try:
        return transcribe_file(wav_path)
    finally:
        try:
            Path(wav_path).unlink(missing_ok=True)
        except Exception:
            pass
