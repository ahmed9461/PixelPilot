# Changelog

## 0.4.0 — 2026-09-17

- Rebuilt PixelPilot from an image-generation controller into a personal multimodal assistant.
- Replaced FLUX/ComfyUI with `Qwen/Qwen3-Omni-30B-A3B-Instruct` served by vLLM.
- Added Telegram text, image, Voice and audio understanding.
- Added RAM-only conversation context and `/new` reset.
- Explicitly removed hidden prompt rewriting: no PixelPilot `system` or `developer` messages are injected.
- Removed FLUX workflows, model manifests, ComfyUI worker/client, seeds, ratios, batches and image-generation UI.
- Updated Vast hardware defaults for the Qwen3-Omni BF16 profile.
- Kept Vast search/rent/start/stop/destroy, recovery, preflight and Cost Guard.
- Updated diagnostics, security docs and tests for the new inference architecture.

## 0.3.1 — 2026-09-14

- Fixed Vast offer-search VRAM query units.

## 0.3.0 — 2026-09-14

- Added secure interactive `.env` configuration helper.
- Hardened Vast lifecycle/reconciliation and provisioning recovery.
- Expanded preflight and offer validation.

## 0.2.0 — 2026-09-13

- Initial Vast lifecycle and image-generation implementation.
