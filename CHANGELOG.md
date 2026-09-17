# Changelog

## 0.4.1 — 2026-09-17

- Switched the default model from `Qwen/Qwen3-Omni-30B-A3B-Instruct` to the much lighter `Qwen/Qwen2.5-Omni-7B`.
- Lowered the default Vast GPU policy from 80GB to 48GB VRAM.
- Lowered the default disk size from 150GB to 80GB.
- Lowered the default Vast price cap from $3.00/h to $0.80/h.
- Reduced the default context from 32768 to 8192 to keep the 48GB profile comfortable.
- Kept text, image and audio understanding and the no-system-prompt behavior unchanged.
- Added a safe `.env` migration helper that updates only non-secret economy-profile settings and creates a backup first.

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
