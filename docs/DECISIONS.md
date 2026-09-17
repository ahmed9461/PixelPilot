# Decisions

## 2026-09-17 — Qwen2.5-Omni-7B as the economical personal default

Use `Qwen/Qwen2.5-Omni-7B` as the default model because the earlier Qwen3-Omni 30B profile forced PixelPilot into 80–96GB GPUs costing about $1/hour in the first live search. The 7B model still understands text, images and audio but allows a 48GB GPU policy and a much lower default Vast price cap.

Keep the 7B profile in BF16 with an 8192-token context by default. Do not silently downgrade to the 3B model: 3B may be added later as an explicit ultra-budget option if the user accepts the quality trade-off.

## 2026-09-17 — No internal prompt

PixelPilot must never add a System Prompt, language instruction, persona or prompt enhancer. The model receives only the actual Telegram conversation supplied by the owner.

## 2026-09-17 — Direct vLLM serving

Remove ComfyUI and the custom FastAPI image Worker. A rented Vast instance serves the configured Qwen Omni model through vLLM's OpenAI-compatible API directly.

## 2026-09-17 — RAM-only chat context

Keep short conversation history only in Controller RAM. Do not persist user messages, images or audio to SQLite. `/new` clears context; Controller restart also clears it.

## 2026-09-17 — Keep Vast lifecycle

Preserve search, review, rent, start, stop, destroy, recovery, preflight and Cost Guard from the previous implementation.
