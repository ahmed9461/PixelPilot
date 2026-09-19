# Progress

## 2026-09-19 — v0.6.0 Qwen3-VL + Whisper quality runtime

Completed in code:
- Switched text/image/video inference to Qwen3-VL-30B-A3B-Instruct-FP8.
- Added Whisper turbo Voice/Audio transcription.
- Added authenticated public gateway with private localhost vLLM.
- Added GPU/CPU Whisper auto-placement.
- Raised context to 16K and disk policy to 100GB while retaining 48GB VRAM and $0.50/hour ceiling.
- Converted audio into transcript before conversation history.
- Added 24-frame video sampling + frame recovery.
- Updated Controller -> Vast environment propagation and bootstrap.
- Updated safe installed-.env migration.
- Updated preflight, docs and test expectations.

Live acceptance after merge:
- Pull v0.6.0 on `/opt/pixelpilot`.
- Run `scripts/migrate_economy_profile.py`.
- Restart Controller.
- Stop/start the existing Vast instance or rent a fresh one so the new bootstrap runs.
- Confirm gateway health reports both Qwen3-VL and Whisper ready.
- Test Arabic conversation, image scene understanding, Voice and video.
- Confirm live streaming and behavior profiles still work.
- Observe A6000 VRAM headroom; if Whisper auto-falls back to CPU, record latency before changing GPU utilization.

## 2026-09-17 — v0.4.2 budget controls and live billing

Completed in code:
- Lowered the hard Vast rental ceiling from $0.80/hour to $0.50/hour.
- Updated the existing `.env` migration helper so an installed controller can adopt the new cap without touching secrets.
- Kept every offer refresh as a real marketplace API request and added comparison against the previous result set.
- Telegram now states whether a refresh returned the same offers, new/removed offers, or changed prices/order.
- Added a per-second rental meter backed by SQLite.
- The meter records active runtime and estimated rental cost from the contracted hourly price, pauses on stop, resumes on start, and stores a final snapshot on destroy.
- Status, provisioning, stop/start, destroy confirmation and final delete messages can show the live meter without exposing implementation details.
- Fixed `diagnose_vast.py` so it no longer treats Vast's constrained execute endpoint as a general-purpose remote shell.
- Added automated tests for the price cap, migration, live refresh comparison and billing arithmetic.

Validation target:
- GitHub Actions compile + pytest.
- Merge to `main` if green.
- Pull `main` on `/opt/pixelpilot`, rerun `scripts/migrate_economy_profile.py`, restart `pixelpilot.service`.
- Verify marketplace search returns only offers at or below $0.50/hour.
- Rent one offer and verify the live timer/cost during provisioning, status, stop/start and destroy.

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
