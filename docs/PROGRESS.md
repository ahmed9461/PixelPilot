# Progress

## 2026-09-17 — v0.4.1 economy profile

Completed in code:
- Switched the default model to `Qwen/Qwen2.5-Omni-7B`.
- Reduced Vast minimum GPU policy to 48GB VRAM.
- Reduced Vast disk default to 80GB.
- Reduced default search price cap to $0.80/hour.
- Reduced model context to 8192 for comfortable single-GPU headroom.
- Kept text/image/audio inputs, direct vLLM serving and no-system-prompt behavior.
- Updated preflight, UI, README, project memory and decisions.
- Added `scripts/migrate_economy_profile.py` to update an existing server `.env` without touching tokens/API keys and with an automatic backup.

Next validation:
- GitHub Actions compile + pytest for the economy branch.
- Merge to `main` if green.
- Pull `main` on `/opt/pixelpilot`, run the migration helper, restart `pixelpilot.service`, then verify Vast search returns 48GB-class offers at a materially lower price.
- First live acceptance of Qwen2.5-Omni-7B with Arabic text, one image and one Telegram Voice message.

## 2026-09-17 — v0.4 multimodal refactor

Completed in code:
- Qwen Omni domain types for text/image/audio input.
- OpenAI-compatible vLLM inference client.
- Direct multimodal Telegram router.
- RAM-only conversation history and `/new`.
- No-system-prompt invariant and tests.
- Vast lifecycle migrated from Worker/ComfyUI to direct inference endpoint.
- Qwen bootstrap script.
- Updated hardware/model environment profile.
- Updated preflight, diagnostics, Cost Guard and UI copy.
- Removed old image-generation paths/resources/tests.
