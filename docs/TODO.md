# TODO

## Live acceptance — economy profile

- Pull the merged v0.4.1 changes on `/opt/pixelpilot`.
- Run `scripts/migrate_economy_profile.py` so the existing `.env` switches from the old 30B/80GB profile without touching secrets.
- Confirm Vast search returns suitable 48 GB offers under the new price cap.
- Rent one reasonably priced 48 GB GPU through the bot.
- Confirm Qwen2.5-Omni-7B reaches READY.
- Test Arabic text conversation.
- Test an Arabic screenshot/photo and follow-up question.
- Test Telegram Voice (OGG/Opus) and an audio file.
- Test `/new` really removes previous context.
- Confirm no message/media content appears in SQLite events.
- Observe actual VRAM use at 8K context before considering any lower-VRAM experimental profile.

## Optional later improvements

- Add an explicit ultra-budget `Qwen2.5-Omni-3B` profile for 24GB-class GPUs only if the user accepts its lower quality.
- Streaming model replies to Telegram.
- Video input.
- Multiple media items in one Telegram request.
- Configurable model profiles without changing the no-system-prompt rule.
