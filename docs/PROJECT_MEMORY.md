# PixelPilot — Project Memory

## Current goal

PixelPilot is an owner-only Telegram image studio backed by temporary Vast.ai GPUs.

Active model:
- `Qwen/Qwen-Image-2.1`

Supported flows:
- text-to-image
- single-image editing
- multi-reference editing with Telegram albums, up to 10 reference images

Output:
- PNG files sent back to Telegram
- seed and output dimensions shown to the owner

## Non-negotiable behavior

1. No assistant personality, emotion, tone, role or chat-style profile is part of image generation.
2. Do not translate, improve, prepend, append or rewrite the user's prompt.
3. Validate that a prompt is non-empty, but send the original prompt string to the model.
4. Do not maintain conversational context or chat history. Each image request is independent.
5. User-facing controls are generation controls: aspect ratio, resolution quality and inference steps.
6. Support up to 10 user-supplied reference images.
7. Preserve PNG output so alpha/transparency is not destroyed.
8. Keep generated/reference image bytes ephemeral; do not persist them in SQLite.
9. Keep Vast lifecycle owner-controlled; automatic deletion is opt-in.
10. `VAST_API_KEY` stays on the controller.
11. The hard rental ceiling remains `$0.50/hour`.
12. Every offer refresh queries the live marketplace.
13. Rental cost is tracked from rent until stop/destroy.
14. The public runtime port is an authenticated PixelPilot image gateway.
15. Qwen-Image loads directly with Diffusers. Do not restore vLLM, Whisper or a chat-completions runtime.

## Hardware policy

- Search minimum: 24 GB VRAM.
- Preferred tier: 48 GB+ VRAM.
- Default disk: 100 GB.
- 24–47 GB: automatic CPU model offload with VAE tiling/slicing.
- 48 GB+: automatic full-GPU placement.
- Default dtype: BF16.
- Default steps: 40.

The BF16 checkpoint components are roughly 33 GB before runtime overhead, so 24 GB requires offload while 48 GB-class GPUs are the practical full-GPU target.

## Image settings

Standard sizes:
- 1:1 — 1024×1024
- 4:3 — 1152×896
- 3:4 — 896×1152
- 3:2 — 1216×832
- 2:3 — 832×1216
- 16:9 — 1344×768
- 9:16 — 768×1344

2K sizes:
- 1:1 — 2048×2048
- 4:3 — 2400×1792
- 3:4 — 1792×2400
- 3:2 — 2528×1696
- 2:3 — 1696×2528
- 16:9 — 2752×1536
- 9:16 — 1536×2752

## Architecture

```text
Telegram owner
  -> PixelPilot Controller
     -> image settings + lifecycle + billing in SQLite
     -> authenticated Vast gateway :8190
        -> QwenImage21Pipeline
           -> CUDA GPU
           -> optional CPU offload when VRAM < 48 GB
```

## Persistence

SQLite stores:
- lifecycle state
- cached Vast offers and refresh metadata
- billing/cost-guard state
- image UI settings
- operational metadata events

SQLite does not store:
- generated image bytes
- reference image bytes
- chat history

## Removed from active project

- Qwen3-VL
- Qwen2.5-Omni
- Whisper
- vLLM
- audio/video understanding
- assistant personalities
- emotions/tone profiles
- reasoning profiles
- language profiles
- custom chat prompts
- chat context/history
- response streaming
