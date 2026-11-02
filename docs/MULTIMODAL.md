# Multimodal migration (Vast.ai price cap: $0.60/hour)

## Scope

This branch changes the owner-only PixelPilot bot from *image-only* to *chat + image understanding + generation + editing*. It preserves existing Vast lifecycle, billed-time estimation, exact Offer-ID confirmation, cost guard and image settings.

The default chat model is `Qwen/Qwen3.5-9B`. The existing Qwen-Image-2.1 image pipeline is retained for editing and transparent PNG generation. It is **not** replaced by the chat model (which cannot edit pixels by itself).

## GPU memory strategy

1. Instance boot loads Qwen3.5 for chat/vision, then announces readiness.
2. Chat and visual questions run on that model with a short history window.
3. On the first image generation/edit request, the gateway releases the chat model and loads Qwen-Image-2.1 on the same GPU.
4. When chat resumes, the worker releases the image pipeline and reloads the chat model.
5. Only one model is resident at a time; no additional GPUs are required. Disk caches must be provisioned to avoid repeated network downloads.

This makes 48GB and 80GB GPUs useful for faster image loading while allowing 24GB with CPU offload as an emergency fallback. A user can opt into `Qwen/Qwen3.5-27B` on larger cards through `CHAT_MODEL_ID`; this increases model download, memory and disk requirements. **No GPU performance was benchmarked in this PR**.

## Search and rental rules

- Strict price <= `VAST_MAX_PRICE_USD_HOUR=0.60` in discovery and revalidation; changing that variable above $0.60 fails configuration validation.
- One GPU, verified offers, min reliability 0.98 and min 1000 Mbps advertised download + 500 Mbps advertised upload, with 3000/1000 then 2000/1000 searches first.
- Search pools: 80GB+, 48GB+, 32GB+, 24GB+; premium-only 80GB and preferred-only 48GB buttons available.
- Results ranked by published DLPerf, GPU VRAM, download/upload speeds, reliability, datacenter flag and price, with a nonzero penalty for unknown inbound transfer cost.
- Rental must match original Offer ID and its live price, GPU, VRAM, speeds and quoted transfer rates. Changed offers require refreshed user confirmation. Unknown upload/download prices are not automatically treated as free.

Storage and traffic may result in extra charges, and speed is not measured by this code.

## Deployment checklist

1. Back up SQLite and your private `.env`. Never commit keys.
2. Run all CPU/controller tests before controller deployment. The owner authorized this deployment without a new paid rental; record GPU acceptance as pending until a specific offer is approved.
3. Install controller update. Check `OWNER_TELEGRAM_ID`, `VAST_API_KEY`, `TELEGRAM_BOT_TOKEN`.
4. Edit an existing `.env`: `VAST_MAX_PRICE_USD_HOUR=0.60`, `CHAT_MODEL_ID=Qwen/Qwen3.5-9B`, `CHAT_MAX_IMAGES=3`, `VAST_MIN_INET_DOWN_MBPS=1000`, `VAST_MIN_INET_UP_MBPS=500`.
5. Keep `PIXELPILOT_REPO_REF=main`; while a reviewed repair PR is pending, pin `PIXELPILOT_WORKER_COMMIT` to its tested full SHA.
6. Run `pytest` and `python -m compileall -q src` on the controller.
7. Only after explicit owner approval of the specific offer, rent a verified GPU with adequate disk and known transfer fees; verify: `/start`, normal chat, image recognition, `/image ...`, and photo caption `/edit ...`.
8. Observe worker logs, GPU OOM, loading time, memory, and Vast billing. Destroy temporary instances explicitly when finished.

## Limitations

- Chat history saves *text only* on the controller and is truncated to the last N turns. Images and visual embeddings are not persisted; follow-up questions about the same image should resend it for accuracy.
- Model switching is synchronous to the worker's inference lock; a second request queues while the first runs.
- No Web search or speech transcription is added by this migration.
- No live Vast rental, billing or real GPU test was run through the GitHub connector alone.
- New workers use per-instance verified TLS; the controller refuses the old public HTTP path. See [DEPLOYMENT_20261103.md](DEPLOYMENT_20261103.md).
