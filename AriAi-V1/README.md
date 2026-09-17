# AriAI — System Prime

Desktop HUD (pywebview + vanilla JS) wired to:

- **LLM / Embeddings** — any OpenAI-compatible `/v1` server (base URL + API key + model, configurable per-endpoint in the "AI Cores" drawer).
- **STT** — [NVIDIA Canary 180M Flash](https://huggingface.co/nvidia/canary-180m-flash), forced onto CPU (`core/stt.py`), so it runs fine on a laptop with no GPU.
- **TTS** — [FreeTTS](https://freetts.org) (`core/tts.py`), no API key required. Long responses are auto-chunked under FreeTTS's 1,000-char free-tier limit and played back sequentially.
- **Web search** — [Ollama Web Search](https://ollama.com) as the primary provider, falling back automatically to [Parallel Search](https://parallel.ai) if Ollama errors or has no key configured (`core/search.py`). The LLM decides when to search via standard OpenAI tool-calling (`core/agent.py`).

## Install

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
# CPU-only torch wheel (smaller download, no CUDA):
pip install torch --index-url https://download.pytorch.org/whl/cpu
```

On Linux you'll also want `ffplay` (part of `ffmpeg`) on PATH for TTS playback,
unless `playsound` works out of the box on your distro.

## Run

```bash
python main.py
```

First launch creates `config.json` next to `main.py` with sane defaults
(see `core/config.py`). Open the **AI Cores Settings** drawer in the UI to
set your LLM/embeddings base URL + key + model, your Ollama/Parallel search
keys, and TTS voice — everything is saved back into `config.json`.

## How a command flows

1. UI (mic or command palette) → `ariai.js: executeCommand()` → `Api.execute_command()` in `main.py`.
2. `core/agent.py` sends the command to your configured LLM with a `web_search` tool available.
3. If the model calls the tool, `core/search.py` hits Ollama Web Search (falling back to Parallel), and the results are fed back to the model for a grounded final answer.
4. The markdown answer + spoken-text + grounding sources are pushed back into the page (`window.onAriResult`) and logged to `logs.json`.
5. If voice output is enabled, the spoken text is sent to FreeTTS (`core/tts.py`), downloaded, and played locally.
6. If **Conversation Mode** is enabled (Voice / TTS tab), the mic re-opens for a short follow-up window (default 5s, configurable) right after Ari finishes speaking. If you say something in that window it's transcribed and fed straight back into step 1-5; if there's silence, it quietly drops back to idle. This is what makes it feel like a back-and-forth instead of one command at a time.

Mic dictation (`Api.start_listening`) records via `sounddevice`, transcribes
with Canary through `core/stt.py`, and feeds the resulting text straight
into the same command pipeline.

## AI Cores Settings

Click **AI Cores Settings** in the topbar to open the settings as a popup
(not an inline panel), with three tabs:
- **AI Cores** — LLM + embeddings base URL / API key / model.
- **Voice / TTS** — STT recording length, follow-up conversation window,
  FreeTTS voice/rate/pitch, and the voice-output / voice-input / conversation-mode toggles.
- **Search** — web grounding toggle, Ollama Web Search key, Parallel Search fallback key.


## Notes / known limits

- Canary 180M Flash is loaded lazily on first use and kept warm in memory;
  the very first transcription will be a few seconds slower than the rest.
- FreeTTS's free tier caps at 1,000 characters per request — `core/tts.py`
  chunks longer text on sentence boundaries automatically.
- The LLM and embeddings endpoints are independently configurable, so you
  can point chat at one provider and embeddings at a cheaper/local one.
