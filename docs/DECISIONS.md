# Decisions

## 2026-09-24 — Qwen-Image-2.1 pivot

PixelPilot is now an image studio rather than a multimodal chat assistant.

### Model
Use `Qwen/Qwen-Image-2.1` through the official Diffusers pipeline family.

### Prompt handling
Pass the user's prompt unchanged after only checking that it contains non-whitespace text. Do not apply assistant personality, emotion, tone, language, reasoning, system prompt, chat context or prompt enhancement.

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
