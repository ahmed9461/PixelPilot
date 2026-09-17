# TODO

## Live acceptance

- Rent one suitable 80 GB+ GPU through the bot.
- Confirm Qwen3-Omni reaches READY.
- Test Arabic text conversation.
- Test an Arabic screenshot/photo and follow-up question.
- Test Telegram Voice (OGG/Opus) and an audio file.
- Test `/new` really removes previous context.
- Confirm no message/media content appears in SQLite events.
- Measure VRAM at 32K context; reduce `MODEL_MAX_LEN` if an 80 GB GPU is too tight.

## Optional later improvements

- Streaming model replies to Telegram.
- Video input.
- Multiple media items in one Telegram request.
- Configurable model profiles without changing the no-system-prompt rule.
