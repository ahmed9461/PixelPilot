# Changelog

## 2026-09-24 — Qwen-Image-2.1

- Pivoted PixelPilot to image generation/editing.
- Added Qwen/Qwen-Image-2.1 through Diffusers.
- Added Standard and 2K image presets.
- Added multi-reference editing for up to 10 Telegram album images.
- Added 24 GB VRAM fallback through CPU offload and 48 GB+ preferred full-GPU profile.
- Added VAE tiling/slicing and PNG delivery.
- Original mode preserved the user's prompt without chat/personality rewriting.
- Removed the previous Qwen3-VL, Whisper and vLLM runtime.
- Removed assistant personality, emotion, tone, reasoning, language and chat-history features.
- Retained Vast lifecycle, billing, recovery, owner-only access and cost guard.

## 2026-09-25 — Safe Vast and optional Qwen enhancement

- Reintroduced live wide-pool discovery, responsive controls and explicit Original/Qwen Enhance settings.
- Fixed selected Offer ID verification, duplicate-rent and start/stop races, ambiguous create recovery and transient status retry.
- Moved optional enhancer downloads behind image readiness, with Original fallback while uncached or on failure.

## 2026-09-26 — Live Vast offer revalidation

- Proved with live raw responses that Vast's `/bundles/` `id` filter returned no row for a simultaneously discoverable Offer ID.
- Persisted the discovery `machine_id` and revalidated within that machine while still requiring the exact original Offer ID.
- Preserved the `$0.50/hour` ceiling, `cancel_unavail=true`, duplicate-rent prevention and ambiguous-create recovery.
