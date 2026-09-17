# Decisions

## 2026-09-17 — Qwen3-Omni as the single personal model

Use `Qwen/Qwen3-Omni-30B-A3B-Instruct` because the project needs one model that can understand text, images and audio and respond with text.

## 2026-09-17 — No internal prompt

PixelPilot must never add a System Prompt, language instruction, persona or prompt enhancer. The model receives only the actual Telegram conversation supplied by the owner.

## 2026-09-17 — Direct vLLM serving

Remove ComfyUI and the custom FastAPI image Worker. A rented Vast instance serves Qwen3-Omni through vLLM's OpenAI-compatible API directly.

## 2026-09-17 — RAM-only chat context

Keep short conversation history only in Controller RAM. Do not persist user messages, images or audio to SQLite. `/new` clears context; Controller restart also clears it.

## 2026-09-17 — Keep Vast lifecycle

Preserve search, review, rent, start, stop, destroy, recovery, preflight and Cost Guard from the previous implementation.
