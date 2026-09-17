# PixelPilot — Project Memory

## Current goal

PixelPilot is a personal, owner-only Telegram assistant backed by a temporary Vast.ai GPU. The active default model is `Qwen/Qwen2.5-Omni-7B` because it provides a better personal-use cost/quality balance than the earlier Qwen3-Omni 30B profile.

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
12. Stable text generation starts at `temperature=0`; the owner may deliberately raise creativity from the Assistant Settings UI. The UI value is stored in SQLite and applies on the next request without editing `.env`.
13. Personality, tone, reasoning depth, formatting, language, custom prompt, context depth and generation controls are runtime owner settings stored in SQLite. Each prompt profile must be viewable, replaceable and resettable from Telegram.

## Architecture

```text
Telegram
  -> PixelPilot Controller
     -> optional owner-configured assistant profile/system message
     -> authenticated public Vast port
     -> vLLM OpenAI-compatible API
     -> Qwen2.5-Omni-7B
```

No ComfyUI, FLUX workflow, image seed/ratio/batch, or PixelPilot Worker is used in v0.5.x.

## Runtime defaults — economy profile

- Model: `Qwen/Qwen2.5-Omni-7B`
- dtype: BF16
- min GPU VRAM policy: 48 GB
- disk: 80 GB
- hard Vast price cap: $0.50/hour
- model context: 8192
- max output tokens: 2048
- creativity: 0% (`temperature=0`)
- diversity: 100% (`top_p=1.0`)
- response-length control: 100% (full configured max output tokens)
- one image, one audio and one video input per prompt by default
- assistant personality/tone/reasoning/format/language: neutral/automatic until owner changes them

The earlier `Qwen/Qwen3-Omni-30B-A3B-Instruct` profile required 80–96GB-class GPUs and proved too expensive for the intended personal-use workflow. Keep 7B as the default unless the user explicitly chooses a higher-cost quality profile later.

## Assistant settings

The main Telegram menu includes `⚙️ إعدادات المساعد` with:
- `🎭 روح المساعد`: editable personality profiles.
- `⚡ السمة`: editable tone profiles.
- `🧠 الاستدلال`: automatic/fast/balanced/deep/critical response approach.
- `🧾 التنسيق`: automatic/compact/structured/steps.
- `🌐 اللغة`: automatic/Arabic/English.
- `🎚️ التوليد`: creativity, diversity and response length percentages.
- `🧠 السياق`: enable/disable RAM-only context, choose retained message depth, clear context.
- `📝 البرومتات`: view/edit/reset current profile prompts, edit a custom prompt layer, view/export the final composed prompt, reset all settings.

Prompt changes take effect on the next request; they do not require GPU reinstall or controller `.env` edits.

## Billing meter

The Controller stores the current rental start time, active interval start, accumulated active seconds, and contracted hourly price in SQLite. The displayed running cost is `active_seconds × hourly_price / 3600` and updates to the current second whenever the user checks status or the lifecycle changes. The final snapshot is kept after instance deletion. Storage and bandwidth can be charged separately by Vast and are not included in this active-rental meter.

## Persistence

SQLite keeps instance lifecycle state, cached Vast offers, offer refresh metadata, operational events, Cost Guard state, billing-meter state, assistant profile selections, editable prompt profiles and generation/context settings. Conversation messages/media remain RAM-only and are not stored in SQLite.
