# PixelPilot — Project Memory

## Current goal

PixelPilot is a personal, owner-only Telegram assistant backed by a temporary Vast.ai GPU. The active default model is `Qwen/Qwen2.5-Omni-7B` because it provides a better personal-use cost/quality balance than the earlier Qwen3-Omni 30B profile.

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
  -> Qwen2.5-Omni-7B
```

No ComfyUI, FLUX workflow, image seed/ratio/batch, or PixelPilot Worker is used in v0.4.x.

## Runtime defaults — economy profile

- Model: `Qwen/Qwen2.5-Omni-7B`
- dtype: BF16
- min GPU VRAM policy: 48 GB
- disk: 80 GB
- default Vast price cap: $0.80/hour
- model context: 8192
- max output tokens: 2048
- one image and one audio input per prompt by default

The earlier `Qwen/Qwen3-Omni-30B-A3B-Instruct` profile required 80–96GB-class GPUs and proved too expensive for the intended personal-use workflow. Keep 7B as the default unless the user explicitly chooses a higher-cost quality profile later.

## Persistence

SQLite keeps instance lifecycle state, cached Vast offers, operational events and Cost Guard state. Conversation content remains RAM-only.
