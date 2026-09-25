# Decisions

## 2026-09-24 — Qwen-Image-2.1 pivot

PixelPilot is now an image studio rather than a multimodal chat assistant.

### Model
Use `Qwen/Qwen-Image-2.1` through the official Diffusers pipeline family.

### Prompt handling
Original mode passes the user's prompt unchanged after non-empty validation. Do not apply assistant personality, emotion, tone, language, reasoning or chat context. Optional Qwen Enhance is selected explicitly.

### GPU policy
- minimum searchable VRAM: 24 GB
- preferred VRAM: 48 GB+
- 24–47 GB uses model CPU offload in automatic mode
- 48 GB+ uses full-GPU placement in automatic mode
- VAE tiling/slicing enabled by default
- BF16 is the default dtype
- rental cap remains $0.50/hour
- disk remains 100 GB

### Quality profiles
Standard mode uses approximately 1K-class dimensions to reduce VRAM pressure and latency. 2K mode uses Qwen-Image-2.1 model-card aspect-ratio dimensions. Default steps remain 40.

### Editing
Support a single reference image and Telegram albums up to 10 references.

### Output
Use PNG rather than JPEG so image quality and alpha/transparency are preserved.

### Removed architecture
Remove vLLM, Whisper, Qwen3-VL, audio/video understanding, assistant profiles, chat history and text-response streaming from active code.


## 2026-09-24 — Optional official Qwen Prompt Enhancer

Add two explicit prompt modes:
- `original`: byte-preserving user prompt path.
- `qwen`: official Qwen prompt rewriting.

Use the official 9B PE checkpoints:
- `Qwen/Qwen-Image-2.1-PE-T2I`
- `Qwen/Qwen-Image-2.1-PE-I2I`

The PE model must not stay resident beside Qwen-Image-2.1. The worker temporarily frees/moves the diffusion pipeline, loads the required PE model on CUDA, rewrites once using the checkpoint's shipped `system_prompt.txt`, unloads it, clears CUDA, restores the diffusion placement, and then generates.

This preserves 24 GB GPU compatibility at the cost of extra latency on enhanced requests. Original mode remains the default and has no extra model download/load cost.


### Official enhancer inference profile

The Transformers path follows Qwen's published `prompt_rewrite/run_transformers.py` contract rather than a simplified text-only approximation:
- both T2I and edit use `AutoProcessor` + `AutoModelForImageTextToText`
- T2I uses presence penalty `1.5` and `max_new_tokens=16256`
- edit uses presence penalty `0` and `max_new_tokens=24000`
- both use temperature `1.0`, top-p `0.95`, top-k `20`, thinking enabled, and seed `42`
- edit references are capped to about 1 megapixel before prompt rewriting, matching Qwen's reference profile
- CPU-offload search requires 48 GB host RAM; full-GPU search does not require a host-RAM floor. Qwen Enhance may need extra RAM and always falls back to Original on failure.

## 2026-09-25 — Offer ID and lifecycle safety

- Search the live Vast marketplace for discovery, then query the exact selected `id` without a ranked result limit before renting. Never silently substitute a similar ask.
- Require a fresh confirmation when price, GPU, or VRAM changes; keep the $0.50/hour ceiling and 24 GB fallback.
- Preserve `cancel_unavail=true`. Treat explicit rejection as safe; keep timeouts, 408/429 and 5xx ambiguous, retaining the label until matching instances can be recovered. No further rent while a label is pending.
- Reserve Telegram lifecycle tasks before awaits; serialize stop/destroy after an in-flight Vast start. Retry isolated status timeouts during provisioning.
- Prefetch optional PE weights after the image worker is ready so Original works immediately. Use Original until the requested checkpoint is cached or after any enhancer failure.
