# PixelPilot architecture

## Controller on the persistent VPS

Owner-only aiogram Telegram routers provide chat, visual questions, generation and editing modes. SQLite stores configuration, per-chat/topic bounded text history, lifecycle reconciliation labels and running-time estimates. Images never enter SQLite.

A single inference gate protects chat and image requests. Lifecycle changes have a separate lock. Automatic idle cleanup revalidates instance identity, activity and worker busy status; explicit manual deletion remains available to stop costs.

## Disposable Vast GPU worker

An authenticated FastAPI gateway starts Qwen3.5-9B for chat/vision. Qwen-Image-2.1 loads on demand for editing/generation. Only one model is resident at once. A single GPU lock serializes model switching and inference. Cancellation drains the executing thread before releasing that lock.

API version 2 advertises chat, vision, image generation and editing capabilities. Health indicates busy/switching rather than treating a transient switch as a dead server. A failed load is not ready.

Authentication occurs before request-body parsing. Body size, image bytes, decoded pixel count, history characters and actual tokenized context all have bounds. EXIF orientation is normalized; image editing preserves alpha when the model produces it.

## Marketplace and paid mutations

Search each VRAM tier with independent price/performance/network orderings, at most three concurrent read requests. Normalize quotes defensively and apply one policy at discovery and immediately before rent. The final rate cannot exceed $0.60/hour; disk allocation is already included in `dph_total`.

Only the exact confirmed Offer ID is rented. Financial/hardware changes require new confirmation; volatile speed measurements are checked against the configured floors. An ambiguous create retains its unique label and blocks another paid create until reconciliation. Failed or ambiguous stop/delete responses retain the instance record instead of falsely reporting success.

## Trust boundaries

Vast keys remain on the VPS. Each GPU has a random bearer token. HTTPS certificate verification is enabled by default when HTTPS is used; the default HTTP transport still requires a trusted tunnel or separately configured TLS for sensitive data. No model weights, production GPU performance or private-network deployment were tested by the CPU-only suite.

The multimodal requirements supersede historical image-only decisions. See [migration](MULTIMODAL.md) and [hardening/acceptance](HARDENING.md).
