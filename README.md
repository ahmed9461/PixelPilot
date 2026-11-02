# PixelPilot — Personal multimodal Telegram assistant

PixelPilot is an **owner-only** Telegram bot for **chat, image understanding, image creation and image editing**. A VPS runs the Telegram controller and stores recent **text** history. An on-demand Vast.ai GPU hosts both neural engines behind a bearer-token protected endpoint.

## Models

| Job | Default | Notes |
| --- | --- | --- |
| Chat / image understanding | [Qwen3.5-9B](https://huggingface.co/Qwen/Qwen3.5-9B) | Image + text and Arabic; configurable via `CHAT_MODEL_ID` |
| Image generation / image editing | [Qwen-Image-2.1](https://huggingface.co/Qwen/Qwen-Image-2.1) | Up to 10 references, original/optional enhancement, PNG and transparency when supported |

Both models run locally **on the rented GPU**, not via a paid LLM API. To avoid requiring two models in VRAM simultaneously, the worker **loads chat first**, unloads it when an image generation/edit is requested, then reloads chat when needed. Model switching can take time; weights remain cached on the Vast storage until the instance is destroyed.

Advanced (optional): `CHAT_MODEL_ID=Qwen/Qwen3.5-27B` for larger GPUs; increase instance disk and select sufficient VRAM. The default 9B is less costly to provision and works on more offers.

## Telegram commands and modes

- Send ordinary text for **chat** with recent text context.
- Send a picture or image document with a question for **visual understanding**. Sending without caption asks the bot to describe it.
- `/image a bird on a wooden bridge` creates an image without changing the mode.
- Caption a photo with `/edit change the background to a beach`, or reply to a photo with `/edit ...`, to **edit it**.
- Menu buttons: **Chat**, **Understand Images**, **Create Images**, **Edit Images**; image generation mode also accepts direct text prompts.
- `/clear` deletes the recent text history. Images themselves are not saved in history.
- Image settings preserve aspect ratio, Standard/2K presets, steps, and the optional Qwen prompt enhancer.

A maximum of 3 images can be submitted at once to visual chat; the image editor accepts up to 10 references. Chat context is intentionally bounded to avoid VRAM exhaustion. History and modes are isolated by Telegram chat/topic. A reply to a previous image reattaches that image; otherwise follow-ups rely on the prior text explanation, not stored pixels. History is bounded to 16,000 characters and actual model input to 8,192 tokens. Combined images are limited to 50 MB per request; pixel bounds are checked before decoding.

## Vast.ai offers and safeguards

**Hard upper limit: $0.60 per GPU hour**, verified at discovery **and again before renting**. This is an hourly rental price ceiling, **not an entire-session bill limit**. Internet egress/ingress, continued storage charges while stopped, and additional downloads may cost extra.

The bot queries price-, performance- and download-sorted 80GB+, 48GB+ and 24GB+ GPU pools (and offers 80GB+ and 48GB+ shortlist buttons), deduplicates asks, and ranks by advertised `dlperf`, GPU VRAM, download/upload speed, host reliability, rental price, and transfer-aware cost. An expensive but powerful GPU may rank above a cheap/slow GPU while remaining under the cap.

Default selection rules:

- Verified offers, reliability >= 98%.
- One GPU, minimum 24GB VRAM, preferred 48GB+, with 80GB+ premium searches.
- At least 150 Mbps **advertised** download and 80 Mbps **advertised** upload; preferred 500/200 Mbps.
- Explicit Offer ID confirmation, revalidation of identity/GPU/price/transfer terms and bandwidth policy before creating the instance, pending-instance reconciliation, and `cancel_unavail=true`.
- Live marketplace quote prices and bandwidth values are **not speed tests** and must not be treated as guaranteed.
- Optional inbound rate ceiling via `VAST_MAX_DOWNLOAD_USD_PER_TB`; unknown transfer prices never count as free.

When the market has no acceptable offer, the bot returns none; it **does not** bypass the hourly cap or rent a weaker unverified instance.

## Deploy

Requires Python 3.11+, controller credentials `TELEGRAM_BOT_TOKEN`, `OWNER_TELEGRAM_ID`, `VAST_API_KEY`, and `PIXELPILOT_REPO_URL` or `VAST_TEMPLATE_HASH`. Copy `.env.example` to `.env` and fill in secrets **outside Git**. `HF_TOKEN` is optional.

```bash
python -m pip install -e .
python scripts/preflight.py
python -m pixelpilot.main
```

For the GPU worker, `scripts/bootstrap_vast.sh` installs Diffusers/Transformers and launches `pixelpilot.inference_gateway:app` on the mapped port. The worker starts the Qwen3.5 chat model and lazily switches to the image pipeline when requested.

**Existing VPS configurations:** old `.env` values override new code defaults, so explicitly change `VAST_MAX_PRICE_USD_HOUR=0.50` to `0.60` if desired, add the chat model settings, and deploy the same Git branch/ref to both controller and new worker. Pushing a commit does not restart a running VPS or upgrade an already rented worker. API-version/capability checks intentionally reject the old image-only worker.

See [the hardening and deployment acceptance report](docs/HARDENING.md), [current architecture](docs/ARCHITECTURE.md), and [migration notes](docs/MULTIMODAL.md). Older image-only decision/progress documents are historical and superseded by this multimodal migration.

## Data, safety and licenses

- The Telegram bot is restricted to the owner ID. Vast credentials remain in the controller, not on the GPU. Worker requests require a per-instance bearer token.
- **Text chat history** resides in the controller's SQLite DB. Images are not written into SQLite; HTTP multipart handling can use temporary files, which are closed after processing. Request bodies are authenticated and bounded before parsing. Telegram and the hosting provider still have their respective data-handling policies.
- The public worker endpoint currently uses HTTP by default unless HTTPS is configured; bearer authentication is **not encryption**. Use a private tunnel/reverse proxy with TLS for sensitive images. Never publish secrets in Git.
- No automatic server destruction unless explicitly enabled in the cost guard; monitor real Vast billing.
- Qwen3.5-9B: [Apache 2.0](https://huggingface.co/Qwen/Qwen3.5-9B). Qwen-Image-2.1: [Qwen Research License](https://huggingface.co/Qwen/Qwen-Image-2.1) — review terms, especially for commercial use.

This is a code-level migration; performance and model-loading latency must still be validated against a rented GPU before declaring production readiness.
