# Changelog

## 0.5.4 — 2026-09-18

- Fixed the v2→v3 persona migration bug that left existing installations on the old behavior prompts even after updating PixelPilot. Prompt schema v4 now recognizes exact v0.5.1/v0.5.2 built-ins and upgrades them while preserving owner-edited prompts.
- Added explicit per-prompt owner-edit markers so future built-in prompt upgrades never overwrite manual edits.
- Sends the active profile as typed system text content, matching Qwen2.5-Omni serving examples.
- Caps video requests at 24 sampled frames and clears older conversation turns before a fresh video request to keep multimodal input inside the 8192-token context.
- Adds a 4096-token-equivalent video pixel budget to new Vast model servers via `VIDEO_MAX_PIXELS`.
- Bumped PixelPilot to 0.5.4 and added migration/video regression tests.


## 0.5.3 — 2026-09-18

- Fixed Qwen2.5-Omni long-response degeneration seen in Arabic storytelling by sending a configurable `repetition_penalty`; the default 50% guard maps to 1.1, matching the model's current vLLM-Omni thinker example.
- Added a `🔁 منع التكرار` generation control (0–100%) to the Telegram settings and Rich Settings dashboard.
- Reworked all personality profiles so each has a visible everyday voice signature instead of activating only in narrow task types.
- Changing personality, tone, reasoning, formatting or language now clears the RAM-only conversation context so the newly selected behavior takes effect immediately instead of inheriting old assistant-style examples.
- Editing or resetting a prompt also starts a clean RAM-only context for the same reason.
- Bumped prompt schema to v3 and PixelPilot to 0.5.3.


## 0.5.2 — 2026-09-18

- Added native Telegram Rich Messages for the home dashboard, Assistant Settings dashboard and completed AI replies, with RTL-aware rendering and plain-text fallback.
- Added live AI response streaming through Telegram `sendMessageDraft`: the answer now appears progressively while vLLM is generating instead of arriving only at the end.
- Draft updates are throttled to avoid hammering Telegram and long previews keep the newest text inside Telegram's draft size limit.
- Added modern Bot API button styles: primary actions are blue, successful/start actions green, and destructive stop/delete/reset actions red on supported Telegram clients.
- Raised the minimum aiogram version to 3.31 so Rich Messages, styled buttons and streaming drafts are available consistently.
- Added streaming-SSE, draft-preview and Rich Message regression tests.


## 0.5.1 — 2026-09-17

- Fixed Assistant Settings navigation so prompt editing returns to the section it came from instead of jumping to an unrelated prompt screen.
- Added explicit navigation origin to prompt view/edit/reset flows and made `/cancel` preserve a sensible return path.
- Removed several Telegram callback glitches: selected options no longer re-edit identical markup, generation value labels are true no-op buttons, and unchanged message edits are ignored safely.
- Added batched SQLite KV reads/writes. Settings screens no longer perform dozens of separate database connections on a single button press.
- Rebuilt the starter personality, tone, reasoning, formatting and language prompts into structured behavior profiles with scope, accuracy rules, adaptation guidance and failure-avoidance constraints.
- Added prompt-schema migration: untouched v0.5.0 starter prompts upgrade automatically, while owner-edited prompts remain unchanged.
- Added navigation, batch-storage, migration and professional-profile regression tests.

## 0.5.0 — 2026-09-17

- Added Telegram video, video-note and video-document understanding using multimodal `video_url` input.
- Enabled one video input per prompt in the Vast vLLM runtime while keeping the previously proven dependency-install path.
- Added a new in-bot Assistant Settings section with personality, tone, reasoning depth, formatting, language, context and generation controls.
- Added editable prompt profiles. The owner can view, replace, reset and export prompts directly from Telegram without SSH or `.env` edits.
- Added a custom prompt layer; the default neutral profile remains prompt-free until the owner enables or edits behavior.
- Added percentage controls for creativity, diversity and response length. Neutral defaults preserve the previous stable behavior: 0% creativity, full diversity and full configured output-token allowance.
- Added runtime context controls: enable/disable memory, choose retained message depth, and clear the current RAM-only context.
- Added regression tests for video payloads, editable profile composition, context policy and generation controls.

## 0.4.3 — 2026-09-17

- Fixed unstable multilingual/gibberish text responses observed in the live Qwen2.5-Omni test.
- PixelPilot now sends `temperature=0` to the inference API so decoding is greedy/deterministic instead of inheriting vLLM's random `temperature=1.0` default.
- This is a generation setting only; PixelPilot still injects no `system` or `developer` prompt and does not rewrite the user's message.
- Added a regression test that verifies both deterministic decoding and the no-internal-prompt invariant.

## 0.4.2 — 2026-09-17

- Lowered the hard Vast rental ceiling to $0.50/hour.
- Made offer refresh visibly live by comparing each fresh marketplace query with the previous results.
- Added per-second active rental time and estimated cost tracking in SQLite.
- Added live billing details to status/provisioning/stop/start/destroy flows and a final billing snapshot after deletion.
- Fixed Vast diagnostics to avoid unsupported remote shell commands and probe the inference endpoint directly.
- Added regression tests for billing arithmetic, offer-refresh comparison, migration and the new price ceiling.

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
