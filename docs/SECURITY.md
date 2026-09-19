# Security and privacy

- Telegram access is owner-only through `OwnerOnlyMiddleware`.
- `VAST_API_KEY` remains on the Controller and is never forwarded to the rented GPU.
- Every rented instance receives a fresh random `PIXELPILOT_INFERENCE_TOKEN`.
- Public port 8190 exposes only the PixelPilot inference gateway and requires the Bearer token.
- vLLM binds to `127.0.0.1:8191`; it is not directly public.
- `HF_TOKEN` is optional and should be read-only if configured.
- `.env` is gitignored and must never be committed.
- PixelPilot does not persist text, image, video, audio, transcripts or model replies in SQLite.
- Audio files are written only to a temporary file on the rented instance for Whisper decoding and deleted in a `finally` block after transcription.
- Chat history lives only in Controller RAM and is reset by `/new`, behavior-profile changes or process restart.
- For Voice/Audio, RAM history stores the transcript text, not the original audio bytes/base64.
- Operational events log only metadata such as instance id, byte/character counts, model and errors; they do not log transcript bodies.
- PixelPilot adds no hidden System/Developer Prompt beyond behavior prompt fragments visible/editable by the owner in Assistant Settings.
- Destroy Vast instances when done to remove remote caches/data and stop active instance billing.
