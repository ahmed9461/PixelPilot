# Architecture

## Controller

Runs permanently on the user's machine/server: aiogram Telegram bot, OwnerOnlyMiddleware, SQLite lifecycle/event state, Vast SDK gateway, Orchestrator, InferenceClient, Cost Guard and RAM-only chat history.

## Temporary Vast instance

1. PixelPilot searches for a matching GPU offer.
2. Owner confirms rent.
3. A random inference API token is generated.
4. Vast starts the configured PyTorch image.
5. `scripts/bootstrap_vast.sh` creates a venv and installs vLLM/Qwen utilities.
6. vLLM downloads/loads `Qwen/Qwen3-Omni-30B-A3B-Instruct`.
7. vLLM binds the mapped port with Bearer-token authentication.
8. Controller probes `/health` and `/v1/models` until ready.

## Chat path

Text is sent as `{role:user, content:<exact text>}`. Image/audio bytes become data URLs in `image_url`/`audio_url` content parts. Caption text is added only when Telegram actually contains a caption.

## Explicitly absent

- System Prompt
- Developer Prompt
- prompt enhancer/translator
- ComfyUI
- FLUX
- image-generation workflow
- custom inference Worker service
