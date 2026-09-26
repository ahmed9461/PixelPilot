# Qwen-Image-2.1 Transition Report

Date: 2026-09-24

## Completed

PixelPilot was converted from a multimodal chat assistant into an owner-only image studio.

Implemented:
- Qwen/Qwen-Image-2.1 runtime
- text-to-image
- one-image editing
- multi-reference editing up to 10 images
- PNG output
- Standard and 2K dimension profiles
- aspect-ratio controls
- 20/30/40/50 step controls
- exact user-prompt pass-through
- 24 GB minimum GPU profile with CPU offload
- 48 GB+ preferred full-GPU profile
- VAE tiling/slicing
- live Vast offer ranking
- existing lifecycle, billing, recovery and cost guard retained

Removed:
- Qwen3-VL
- Whisper
- vLLM
- audio/video input flows
- assistant personalities and tone/emotion settings
- reasoning/language/chat settings
- conversation history and streamed text responses

## Validation

GitHub Actions reached successful full test runs after the code transition and cleanup.

## Deployment status

This report records the initial transition as of 2026-09-24. The Qwen-Image-2.1 stable version subsequently reached `main`. For the current selective Vast and optional enhancer improvements, see `PROGRESS.md` and `RUNBOOK.md`; a live Vast smoke test remains pending.
