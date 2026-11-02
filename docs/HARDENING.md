# Multimodal hardening — 2026-11-03

This work hardens the multimodal baseline merged through PR #23. The follow-up changes live on `fix/multimodal-hardening-20261103`; they do not deploy the VPS, rent a GPU, or merge into production `main`.

## Root causes and fixes

| Root cause | Change |
| --- | --- |
| Stored chat could grow to 64,000 characters but the worker rejected history over 16,000 | Shared contracts retain complete recent exchanges within 16,000 characters; tokenized input is checked separately against 8,192 tokens. |
| Independent chat/image locks overwrote the same `inference.active` flag | One controller inference gate, with cleanup in `finally`; /clear waits for an in-flight exchange before clearing it. |
| Cancelling `asyncio.to_thread` does not stop the model/CUDA thread | Shield and drain model work before releasing the worker lock, including repeated cancellation. |
| A model switch temporarily looked like a broken server | Health distinguishes switching/busy from failure; controller verifies API version 2 and both model capabilities, rejecting an old image-only worker. |
| Global history could mix different Telegram chats/topics | Scope history and selected mode by chat/topic. No image pixels are persisted in conversation history. |
| A cheapest-only market pool excluded faster offers before local ranking | Query price, DLPerf and download orderings in each 24GB+/48GB+/80GB+ tier; cap concurrency at three, deduplicate and rank. |
| Permissive quote parsing could accept `"false"`, nonfinite metrics, or a base price excluding disk | Parse booleans/numbers explicitly; require `dph_total`; share a fail-closed policy for discovery and pre-rent validation. |
| Small speed/reliability changes required repeated confirmation despite unchanged financial terms | Reconfirm identity/hardware/price/transfer changes; recheck volatile metrics against minimum policy without requiring exact equality. |
| CPU RAM, direct ports, disk capacity or GPU count could be missing | Exclude incomplete required hardware data; offload GPUs require known sufficient host RAM. |
| Stop/delete responses were ignored | Require an explicit successful acknowledgement; failed/ambiguous lifecycle requests keep instance and billing tracking. |
| Idle cleanup used a stale observation | Recheck instance identity, activity timestamp, controller gate and worker busy status under the lifecycle lock. Manual deletion remains possible. |
| Upload size was checked only after downloading; image pixels only after decoding | Bounded download buffer, pre-body worker authentication, aggregate 50 MB limit, 25-million-pixel check before decoding, EXIF orientation handling. |
| Validation responses could echo private request fields | Return generic validation details; disable public interactive API docs; no bearer redirects; TLS certificate checking defaults on for HTTPS. |
| Telegram image documents in albums were treated as photos; edit-mode text could enter chat | Handle both media types, debounce bounded albums, route explicit edits correctly, preserve Original prompt whitespace, split replies by UTF-16 units. |
| Bootstrap defaults masked Vast PID-1 configuration; duplicate startup could download twice | Recover environment before defaults, use a startup lock, check CUDA/Python/imports, avoid broad process killing, and mark dependency setup complete only after checks pass. |

## Validation

The local GPU-free regression selection passed **132 tests** on Python 3.13 before publication. The complete suite runs on GitHub Actions for Python 3.11 and 3.12; consult the checks attached to the final PR head, not a previous green commit. CI retains JUnit output and a tracked-source-only ZIP for seven days.

Tests use fake Vast/Telegram/inference adapters. They do not establish real GPU model-load success, latency, image quality, network throughput, provider billing accuracy, or end-to-end production readiness.

## Deliberate boundaries

- The default models remain `Qwen/Qwen3.5-9B` and `Qwen/Qwen-Image-2.1`. A larger configurable model still needs its own memory/disk sizing and live acceptance test.
- $0.60/hour is the hard quoted rental-rate ceiling, including requested disk in `dph_total`. Data transfer and stopped-storage costs are not an all-in spending cap.
- Published network and DLPerf values are not speed tests. No acceptable offer means no rental; the bot does not bypass the cap.
- HTTP is still available for compatibility. Authentication is not encryption: use HTTPS with valid certificates or a trusted private tunnel for sensitive media. The preflight warning does not configure a tunnel.
- Diffusers installation follows the official model's Git installation requirement. The worker dependency stack and container still need a real GPU smoke test and a frozen validated runtime image before production rollout.
- `/clear` removes active conversation history logically; it is not forensic erasure of SQLite pages, backups or Telegram messages.
- Failed or ambiguous rentals are not blindly retried. Automatic destruction remains opt-in; no unrelated instance is touched.

## Deployment acceptance

Back up the private `.env` and SQLite. Controller and worker must use the same tested Git ref. Existing `.env` values override new defaults: explicitly choose `VAST_MAX_PRICE_USD_HOUR=0.60`, configure `CHAT_MODEL_ID`, and prefer verified TLS/private networking. Re-provision the old image-only worker.

Before merging/deploying: verify real chat, an image question, follow-up by replying to that image, `/image`, `/edit`, a multi-image album, model switching in both directions, manual delete, and actual Vast charges. A green CPU suite is necessary, not sufficient, for that acceptance.
