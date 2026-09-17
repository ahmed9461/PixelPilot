# Decisions

## 2026-09-17 — Deterministic Qwen text decoding

PixelPilot sends `temperature=0` on chat-completion requests. vLLM defaults to `temperature=1.0`, which samples randomly; the live Arabic test produced intermittent multilingual/gibberish output under that default. Qwen2.5-Omni's official Transformers examples use `model.generate()` without enabling sampling, so greedy decoding is the closer behavioral match.

This is a generation/sampling control only. It must not be implemented as a System Prompt, language instruction, hidden user-message rewrite, or any other injected message.

## 2026-09-17 — $0.50/hour hard rental ceiling

PixelPilot must not rent any offer whose total hourly rental price exceeds `$0.50/hour`. The ceiling is enforced both in marketplace search and again immediately before instance creation so a stale cached offer cannot bypass it.

## 2026-09-17 — Live marketplace refresh feedback

Every press of the refresh/search button must perform a new marketplace request. PixelPilot compares the fresh result set with the previous cached result set and tells the user whether nothing changed, offers appeared/disappeared, or prices/order changed. Do not fake rotation or shuffle unchanged offers just to make refresh look different.

## 2026-09-17 — Per-second rental meter

Track the active rental meter in SQLite from successful contract creation through stop/destroy. The meter uses the contracted hourly price and accumulated active seconds, pauses when the user stops the instance, resumes on start, and stores a final snapshot on destroy. Telegram status and destroy confirmation show the current elapsed active time and estimated rental cost. Storage and bandwidth remain separate provider charges and are not included in this meter.

## 2026-09-17 — Keep Telegram UI user-facing

Normal Telegram screens must contain only information the user needs to operate PixelPilot. Do not expose model names, vLLM/inference architecture, prompt-policy explanations, deployment internals, or implementation notes in welcome/help/status/provisioning screens. Keep technical details in `README`, `docs`, logs, diagnostics and developer-facing files instead.

Hardware details that are necessary to choose a rented server — GPU name, VRAM, price, reliability, network speed and location — may remain in the offer screen.

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
