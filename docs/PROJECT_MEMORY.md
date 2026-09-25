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
2. Raw mode remains available and must send the user's prompt unchanged.
3. Official Qwen Prompt Enhancer is an explicit owner-controlled mode, never a hidden layer. When enabled, use only Qwen/Qwen-Image-2.1-PE-T2I for text-to-image or Qwen/Qwen-Image-2.1-PE-I2I for editing, together with the system_prompt.txt shipped by that model.
4. Do not maintain conversational context or chat history. Each image request is independent.
5. User-facing controls are generation controls: aspect ratio, resolution quality, inference steps, and prompt mode (Original or Official Qwen Enhance).
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
- Default disk: 100 GB. Optional enhancer weights prefetch in the background after image readiness; monitor free space if both caches are used.
- Minimum host RAM filter: 48 GB for CPU-offload offers; no unconditional host-RAM floor on full-GPU offers. More RAM may help Qwen Enhance.
- 24–47 GB VRAM: automatic CPU model offload with VAE tiling/slicing.
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
        -> on-demand official Qwen 9B prompt enhancer
           -> loaded only for rewrite, then released before diffusion
```

## Persistence

SQLite stores:
- lifecycle state
- latest Vast offer snapshot and refresh metadata (never used as the live rent check)
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


## Official prompt enhancer

- Mode is stored in SQLite and defaults to `original`.
- `original`: prompt reaches Qwen-Image unchanged.
- `qwen`: use the official Qwen prompt enhancer before generation.
- T2I enhancer: `Qwen/Qwen-Image-2.1-PE-T2I`.
- I2I enhancer: `Qwen/Qwen-Image-2.1-PE-I2I`.
- Checkpoints download in the background after image readiness. Until the selected T2I/I2I model is cached, the original prompt is used. The enhancer loads on demand for one rewrite and then releases CUDA before generation.
- Enhancer failures always fall back to the original prompt.
- Do not persist original or rewritten prompt bodies to SQLite.


## Vast offer discovery

- Telegram should display only the best 8 offers, but discovery must scan a wider live candidate pool.
- Normal search performs a dedicated 48 GB+ query plus a 24 GB+ fallback query, deduplicates results, then ranks 48 GB+ first.
- A separate owner-controlled “48 GB+ only” search mode is available from the offer list.
- Search refreshes must remain live; do not rotate cached results to simulate market changes.
- Offer cards show the actual Offer ID so equal GPU, price and reliability labels remain distinguishable.
- Rental checks query the exact selected Offer ID, independently of the ranked discovery limit; changed price/GPU/VRAM requires renewed confirmation.
- Exact-ID structured SDK searches explicitly use the discovery baseline (`verified=true`, `external=false`, `rentable=true`) with `no_default=true`; otherwise the SDK adds a `rented=false` constraint that discovery did not use.
- Explicit 4xx rejection can clear pending state; network, 408/429 and 5xx outcomes retain the unique label and block another rent until reconciliation.
- Rapid refresh clicks should not launch overlapping marketplace searches.


## Telegram server-control responsiveness

- Long Vast lifecycle waits must never occupy a Telegram callback handler.
- Rent/provision and start/wait operations run as named background tasks.
- Server status uses a short probe timeout and must return quickly even while the image endpoint is still booting.
- Rapid repeated lifecycle button clicks must not create duplicate provisioning/start tasks.
- The owner must retain access to status/stop/destroy controls while provisioning is active.
- Reserve the lifecycle task before any callback await; wait for in-flight Vast start mutations before stop/destroy. Retry transient status timeouts through the overall readiness deadline.
