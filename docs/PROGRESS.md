# Progress

## 2026-09-17 — v0.4 multimodal refactor

Completed in code:
- Qwen3-Omni domain types for text/image/audio input.
- OpenAI-compatible vLLM inference client.
- Direct multimodal Telegram router.
- RAM-only conversation history and `/new`.
- No-system-prompt invariant and tests.
- Vast lifecycle migrated from Worker/ComfyUI to direct inference endpoint.
- Qwen3-Omni bootstrap script.
- Updated hardware/model environment profile.
- Updated preflight, diagnostics, Cost Guard and UI copy.
- Removed old image-generation paths/resources/tests.

Validation target: compile Python/scripts, bash syntax check, pytest via GitHub Actions, then first live Vast acceptance.
