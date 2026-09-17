# PixelPilot — Project Memory

## Current goal

PixelPilot is a personal, owner-only Telegram assistant backed by a temporary Vast.ai GPU. The active model is `Qwen/Qwen3-Omni-30B-A3B-Instruct`.

Supported user inputs:
- text
- images
- Telegram Voice
- audio files

Output is text. Image generation is no longer part of the project.

## Non-negotiable behavior

1. Do not inject a System Prompt or Developer Prompt.
2. Do not translate, improve, prepend, append or rewrite the user's message before sending it to Qwen.
3. A media-only message must remain media-only; do not invent a hidden “describe this” instruction.
4. Conversation content is RAM-only on the Controller, not persisted to SQLite.
5. `/new` clears the current conversation context.
6. Vast lifecycle remains owner-controlled; automatic destruction is opt-in.
7. `VAST_API_KEY` stays on the Controller.

## Architecture

```text
Telegram
  -> PixelPilot Controller
  -> authenticated public Vast port
  -> vLLM OpenAI-compatible API
  -> Qwen3-Omni
```

No ComfyUI, FLUX workflow, image seed/ratio/batch, or PixelPilot Worker is used in v0.4.

## Runtime defaults

- Model: `Qwen/Qwen3-Omni-30B-A3B-Instruct`
- dtype: BF16
- min GPU VRAM policy: 80 GB
- disk: 150 GB
- model context: 32768
- max output tokens: 2048
- one image and one audio input per prompt by default

## Persistence

SQLite keeps instance lifecycle state, cached Vast offers, operational events and Cost Guard state. Conversation content remains RAM-only.
