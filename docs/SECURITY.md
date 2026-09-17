# Security and privacy

- Telegram access is owner-only through `OwnerOnlyMiddleware`.
- `VAST_API_KEY` remains on the Controller and is never forwarded to the rented GPU.
- Every rented instance receives a fresh random `PIXELPILOT_INFERENCE_TOKEN`.
- vLLM requires this token through Bearer authentication.
- `HF_TOKEN` is optional and should be read-only if configured.
- `.env` is gitignored and must never be committed.
- PixelPilot does not persist text, image, audio, or model replies in SQLite.
- Chat history lives only in Controller RAM and is reset by `/new` or process restart.
- Operational events log only metadata such as instance id, message count, model and response character count.
- PixelPilot adds no hidden System/Developer Prompt.
- Destroy Vast instances when done to remove remote cache/data and stop instance billing.
