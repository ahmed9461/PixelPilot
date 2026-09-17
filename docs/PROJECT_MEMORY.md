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
8. Telegram UI copy must stay user-facing. Do not put model names, inference architecture, prompt-policy explanations, deployment details, or implementation notes in normal bot screens. Keep those details in `README`, `docs`, logs, and diagnostic tools.
9. The rental hard ceiling is `$0.50/hour`. PixelPilot must reject any cached/selected offer above that ceiling even if it was visible in an older search.
10. Offer refresh must perform a fresh marketplace query every time. Compare the new result set with the previously cached set and tell the user whether offers/prices/order actually changed.
11. Track rental time and estimated active rental cost per second from rent until stop/destroy. Pausing stops the active-time meter; restarting resumes it. Preserve the final billing snapshot after destroy.

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
- hard Vast price cap: $0.50/hour
- model context: 8192
- max output tokens: 2048
- one image and one audio input per prompt by default

The earlier `Qwen/Qwen3-Omni-30B-A3B-Instruct` profile required 80–96GB-class GPUs and proved too expensive for the intended personal-use workflow. Keep 7B as the default unless the user explicitly chooses a higher-cost quality profile later.

## Billing meter

The Controller stores the current rental start time, active interval start, accumulated active seconds, and contracted hourly price in SQLite. The displayed running cost is `active_seconds × hourly_price / 3600` and updates to the current second whenever the user checks status or the lifecycle changes. The final snapshot is kept after instance deletion. Storage and bandwidth can be charged separately by Vast and are not included in this active-rental meter.

## Persistence

SQLite keeps instance lifecycle state, cached Vast offers, offer refresh metadata, operational events, Cost Guard state, and billing-meter state. Conversation content remains RAM-only.
