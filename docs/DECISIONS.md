# Decisions

## 2026-09-17 — Owner-controlled prompt profiles supersede the blanket no-prompt rule

The earlier “No internal prompt” decision is superseded by the owner's request for editable assistant personalities and behavior controls. The neutral/default profile still injects no prompt. When the owner explicitly selects a personality, tone, reasoning, formatting, language profile or custom prompt, PixelPilot may compose those visible/editable pieces into one `system` message for the request.

Every injected prompt fragment must be visible, editable, replaceable and resettable from Telegram. PixelPilot must never add a second hidden System/Developer Prompt or silently rewrite the user's actual message. Prompt selections and edited templates are stored in SQLite so changing behavior never requires SSH or `.env` edits.

## 2026-09-17 — Video is a first-class multimodal input

Support Telegram videos, video notes and video documents. Pass video bytes to the OpenAI-compatible endpoint as a `video_url` data URL and allow one video per prompt by default. Keep the same media-size guard used for images/audio. The Vast runtime includes video in `--limit-mm-per-prompt` while keeping the previously proven dependency-install path.

## 2026-09-17 — Runtime generation controls live in Telegram

Expose user-facing percentage controls for creativity, diversity and response length. The neutral defaults must preserve the already-tested v0.4.3 behavior: creativity 0% maps to `temperature=0`, diversity 100% maps to `top_p=1.0`, and response length 100% keeps the full configured output-token allowance. The owner can deliberately change any of these from Telegram. These are request-time controls stored in SQLite, not `.env` mutations.

## 2026-09-17 — Deterministic Qwen text decoding

PixelPilot sends `temperature=0` on chat-completion requests by default. vLLM defaults to `temperature=1.0`, which samples randomly; the live Arabic test produced intermittent multilingual/gibberish output under that default. Qwen2.5-Omni's official Transformers examples use `model.generate()` without enabling sampling, so greedy decoding is the closer behavioral match.

This is a generation/sampling control. The owner may later increase creativity explicitly through Assistant Settings.

## 2026-09-17 — $0.50/hour hard rental ceiling

PixelPilot must not rent any offer whose total hourly rental price exceeds `$0.50/hour`. The ceiling is enforced both in marketplace search and again immediately before instance creation so a stale cached offer cannot bypass it.

## 2026-09-17 — Live marketplace refresh feedback

Every press of the refresh/search button must perform a new marketplace request. PixelPilot compares the fresh result set with the previous cached result set and tells the user whether nothing changed, offers appeared/disappeared, or prices/order changed. Do not fake rotation or shuffle unchanged offers just to make refresh look different.

## 2026-09-17 — Per-second rental meter

Track the active rental meter in SQLite from successful contract creation through stop/destroy. The meter uses the contracted hourly price and accumulated active seconds, pauses when the user stops the instance, resumes on start, and stores a final snapshot on destroy. Telegram status and destroy confirmation show the current elapsed active time and estimated rental cost. Storage and bandwidth remain separate provider charges and are not included in this meter.

## 2026-09-17 — Keep Telegram UI user-facing

Normal Telegram screens must contain only information the user needs to operate PixelPilot. Do not expose model names, vLLM/inference architecture, deployment internals, or implementation notes in welcome/help/status/provisioning screens. Keep technical details in `README`, `docs`, logs, diagnostics and developer-facing files instead.

Assistant behavior controls such as personality, tone, reasoning depth, formatting, language, context and generation percentages are intentionally user-facing and belong in the settings UI.

Hardware details that are necessary to choose a rented server — GPU name, VRAM, price, reliability, network speed and location — may remain in the offer screen.

## 2026-09-17 — Qwen2.5-Omni-7B as the economical personal default

Use `Qwen/Qwen2.5-Omni-7B` as the default model because the earlier Qwen3-Omni 30B profile forced PixelPilot into 80–96GB GPUs costing about $1/hour in the first live search. The 7B model still understands text, images, audio and video but allows a 48GB GPU policy and a much lower Vast price cap.

Keep the 7B profile in BF16 with an 8192-token context by default. Do not silently downgrade to the 3B model: 3B may be added later as an explicit ultra-budget option if the user accepts the quality trade-off.

## 2026-09-17 — No internal prompt (historical, superseded)

Originally PixelPilot was required to never add a System Prompt, language instruction, persona or prompt enhancer. This decision was later superseded by the owner-controlled prompt-profile decision above. Its core privacy principle remains: no hidden prompt or silent rewrite outside what the owner can see/edit in Telegram.

## 2026-09-17 — Direct vLLM serving

Remove ComfyUI and the custom FastAPI image Worker. A rented Vast instance serves the configured Qwen Omni model through vLLM's OpenAI-compatible API directly.

## 2026-09-17 — RAM-only chat context

Keep conversation messages/media only in Controller RAM. Do not persist user messages, images, audio or video to SQLite. `/new` and the context-clear button clear context; Controller restart also clears it. Persist only context settings (enabled/disabled and message depth), not conversation content.

## 2026-09-17 — Keep Vast lifecycle

Preserve search, review, rent, start, stop, destroy, recovery, preflight and Cost Guard from the previous implementation.
