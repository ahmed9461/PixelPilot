# Security and privacy

- Telegram access is owner-only through `OwnerOnlyMiddleware`.
- `VAST_API_KEY` remains on the controller and is never forwarded to the rented GPU.
- Every rented instance receives a fresh random `PIXELPILOT_INFERENCE_TOKEN`.
- Public port 8190 exposes only the authenticated PixelPilot image gateway.
- `HF_TOKEN` is optional and should be read-only if configured.
- `.env` is gitignored and must never be committed.
- PixelPilot does not persist generated image bytes or reference image bytes in SQLite.
- Telegram album reference images live only in controller RAM while that request is assembled and processed.
- Operational events store metadata such as instance id, dimensions, seed, reference count and errors rather than image bytes.
- Image requests do not use assistant personality, tone, emotion, chat history or prompt-rewrite layers.
- The prompt sent to the image worker is the prompt supplied by the owner after non-empty validation.
- Destroy temporary GPU instances when finished to stop active instance billing and remove remote runtime/cache state according to provider behavior.

## Multimodal TLS deployment (2026-11-03)

New workers require per-instance verified TLS; public plaintext fallback is refused. The controller pins its issued certificate while keeping existing API credentials. Root-private SQLite holds owner-scoped bounded chat text; images remain ephemeral. See [DEPLOYMENT_20261103.md](DEPLOYMENT_20261103.md) for trust, backups and limitations.
