# PixelPilot — Project Memory

## Current goal

PixelPilot is a personal, owner-only Telegram assistant backed by a temporary Vast.ai GPU. The active quality profile is `Qwen/Qwen3-VL-30B-A3B-Instruct-FP8` for text/image/video plus OpenAI Whisper `turbo` for Voice/Audio transcription. This replaced Qwen2.5-Omni-7B after live testing showed inadequate instruction/context and visual-understanding quality.

Supported user inputs:
- text
- images
- Telegram Voice
- audio files
- videos and Telegram video notes

Output is text. Image generation is no longer part of the project.

## Non-negotiable behavior

1. The default neutral assistant profile is prompt-free. PixelPilot may inject only prompt text that is visible/editable by the owner through the in-bot Assistant Settings UI; never add an extra hidden System/Developer Prompt behind those settings.
2. Do not translate, improve, prepend, append or rewrite the user's actual message before sending it to Qwen.
3. A media-only message must remain media-only; do not invent a hidden “describe this” instruction.
4. Conversation content is RAM-only on the Controller, not persisted to SQLite.
5. `/new` and the in-bot context-clear action clear the current conversation context.
6. Vast lifecycle remains owner-controlled; automatic destruction is opt-in.
7. `VAST_API_KEY` stays on the Controller.
8. Telegram UI copy must stay user-facing. Do not put model names, inference architecture, deployment details, or implementation notes in normal bot screens. Keep those details in `README`, `docs`, logs, and diagnostic tools. Assistant behavior/generation controls are user-facing and belong in the Assistant Settings UI.
9. The rental hard ceiling is `$0.50/hour`. PixelPilot must reject any cached/selected offer above that ceiling even if it was visible in an older search.
10. Offer refresh must perform a fresh marketplace query every time. Compare the new result set with the previously cached set and tell the user whether offers/prices/order actually changed.
11. Track rental time and estimated active rental cost per second from rent until stop/destroy. Pausing stops the active-time meter; restarting resumes it. Preserve the final billing snapshot after destroy.
12. Qwen3-VL generation starts from its published profile: `temperature=0.7`, `top_p=0.8`, `top_k=20`, `repetition_penalty=1.0`. The owner can change creativity/diversity/repetition controls from Telegram; owner-edited values survive automatic profile migrations.
13. Personality, tone, reasoning depth, formatting, language, custom prompt, context depth and generation controls are runtime owner settings stored in SQLite. Each prompt profile must be viewable, replaceable and resettable from Telegram.
14. Assistant Settings navigation must be deterministic: a Back button returns to the screen that opened the current screen. Prompt edit/view/reset flows must preserve whether they came from a behavior group or the central prompt hub.
15. Settings callbacks must feel immediate. Avoid repeated SQLite open/read cycles and avoid Telegram edits that intentionally submit identical text/markup. Use batched KV operations and safe no-op handling.
16. Built-in behavior profiles are production-quality modular behavior contracts, not one-line style hints. They should define scope, desired behavior, accuracy/adaptation rules and what to avoid, while remaining compact enough to compose without wasting the 16K context window.
17. PixelPilot is visual-first. Prefer Telegram-native Rich Messages, structured dashboards and styled action buttons over plain walls of text whenever the feature is available, while preserving a graceful plain-message fallback.
18. AI replies stream live through Telegram message drafts while vLLM generates. Draft updates must be throttled, ephemeral, and followed by one persistent final response.
19. Qwen generation uses an owner-adjustable repetition guard. Qwen3-VL starts at 0% (`repetition_penalty=1.0`); the control can raise the penalty to 1.2 if a future workload needs stronger loop suppression.
20. Personality/tone/reasoning/format/language changes start a new RAM-only conversation context. A new behavior profile must not be diluted by assistant messages generated under the previous profile.
21. Persona profiles must have an observable everyday voice signature. Task adaptation may reduce stylistic intensity for technical/sensitive work, but it must not make different personalities indistinguishable in normal conversation.
22. Prompt migrations are versioned and must recognize the immediately previous built-in prompt values. Manual prompt edits are tracked with explicit edit markers and must never be overwritten by automatic schema upgrades.
23. Video requests reserve context aggressively: sample 24 frames and discard older conversation turns before a new video turn.
24. Qwen3-VL handles text/image/video only. Voice/Audio must be transcribed by Whisper turbo first; the transcript, not raw audio, enters Qwen chat history.
25. The public Vast port is a PixelPilot inference gateway. vLLM binds localhost only; the gateway owns auth, speech transcription and proxying.
26. Runtime target is 48GB+ VRAM, 100GB disk, 16K model context and $0.50/hour hard rental ceiling.
27. Qwen2.5-Omni-7B is retired as the default because live personal-use testing showed insufficient general understanding, context following and non-text visual interpretation.

## Architecture

```text
Telegram
  -> Rich Message UI + live response drafts
  -> PixelPilot Controller
     -> optional owner-visible/editable behavior profile
     -> authenticated public Vast gateway :8190
        -> Whisper turbo for Voice/Audio
        -> private vLLM :8191
           -> Qwen3-VL-30B-A3B-Instruct-FP8
```

## Runtime defaults — quality profile

- Vision-language model: `Qwen/Qwen3-VL-30B-A3B-Instruct-FP8`
- Speech model: Whisper `turbo`
- min GPU VRAM policy: 48 GB
- disk: 100 GB
- hard Vast price cap: $0.50/hour
- model context: 16384
- max output tokens: 2048
- vLLM GPU utilization: 0.82
- Whisper device: auto (CUDA when safe, CPU fallback)
- one image and one video per prompt
- video sampling: 24 frames with frame recovery
- assistant personality/tone/reasoning/format/language: neutral/automatic until owner changes them

## Assistant settings

The main Telegram menu includes `⚙️ إعدادات المساعد` with:
- `🎭 روح المساعد`: editable personality profiles.
- `⚡ السمة`: editable tone profiles.
- `🧠 الاستدلال`: automatic/fast/balanced/deep/critical response approach.
- `🧾 التنسيق`: automatic/compact/structured/steps.
- `🌐 اللغة`: automatic/Arabic/English.
- `🎚️ التوليد`: creativity, diversity, response length and repetition-guard percentages. Qwen3-VL defaults are 70% / 80% / 100% / 0%.
- `🧠 السياق`: enable/disable RAM-only context, choose retained message depth, clear context.
- `📝 البرومتات`: view/edit/reset current profile prompts, edit a custom prompt layer, view/export the final composed prompt, reset all settings.

Prompt changes take effect on the next request; they do not require GPU reinstall or controller `.env` edits. The built-in v0.5.1 profiles use structured behavior contracts rather than short style sentences. A prompt-schema version is stored so untouched old starter prompts can be upgraded without overwriting owner customizations.

## Settings performance

Assistant settings use batched `get_many` / `set_many` SQLite operations for profile state. A screen should not open a fresh SQLite connection for every individual setting. Buttons that represent the already-selected value are treated as no-ops, and harmless Telegram `message is not modified` responses are ignored rather than surfaced as glitches.

## Telegram visual UX

PixelPilot targets Bot API 10.x features through aiogram 3.31+:
- `/start` uses a native RTL Rich Message card with a collapsible capabilities section.
- Assistant Settings opens as a Rich Message dashboard with a compact status table.
- Main actions use Telegram button styles (`primary`, `success`, `danger`) where appropriate.
- AI output is streamed through `sendMessageDraft` while generation is in progress, then persisted as a native Rich Message when complete.
- If Rich Message rendering or draft streaming fails, fall back to the reliable classic text-message path instead of losing the response.
- Do not update a draft for every token; throttle updates to keep the UI smooth and avoid Telegram rate-limit pressure.

## Billing meter

The Controller stores the current rental start time, active interval start, accumulated active seconds, and contracted hourly price in SQLite. The displayed running cost is `active_seconds × hourly_price / 3600` and updates to the current second whenever the user checks status or the lifecycle changes. The final snapshot is kept after instance deletion. Storage and bandwidth can be charged separately by Vast and are not included in this active-rental meter.

## Persistence

SQLite keeps instance lifecycle state, cached Vast offers, offer refresh metadata, operational events, Cost Guard state, billing-meter state, assistant profile selections, editable prompt profiles and generation/context settings. Conversation messages/media remain RAM-only and are not stored in SQLite.
