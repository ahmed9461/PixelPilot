# Test Plan

Automated tests cover settings validation, exact user-message construction without System Prompt, image/audio data URLs, media-only messages without invented instructions, exact inference payloads, Vast lifecycle/recovery, optional HF token setup, preflight and chat-history trimming.

Existing Vast query normalization, database, security and callback regression tests remain.

CI runs compileall + pytest on Python 3.12. Live acceptance additionally tests Arabic text, screenshots/photos and Telegram Voice on a real rented GPU.
