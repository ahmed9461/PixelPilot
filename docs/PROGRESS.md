# Progress

## 2026-09-24 — Qwen-Image-2.1 transition

Completed on branch `qwen-image-2.1-transition`:

- replaced Qwen3-VL/Whisper/vLLM settings with Qwen-Image-2.1 settings
- lowered viable Vast search floor to 24 GB VRAM
- added preferred 48 GB+ VRAM tier and offer ranking
- added automatic full-GPU vs CPU-offload selection
- enabled VAE tiling and slicing
- replaced chat inference client with image generation/edit client
- replaced runtime gateway with `QwenImage21Pipeline`
- replaced Telegram chat UX with text-to-image and image editing
- added Telegram album multi-reference editing up to 10 images
- added Standard/2K, aspect ratio and inference-step settings
- removed personality/emotion/tone/reasoning/chat-history modules
- removed Whisper/audio/video paths
- updated preflight, environment profile and tests
- CI reached a successful run after the code cleanup
- project memory and README updated for the new architecture

Deployment note:
The repository branch is ready for integration, but the persistent controller must be updated together with `main`. Merging a new GPU runtime while leaving an old controller process running would create a protocol mismatch on the next rental.


## 2026-09-24 — Official Qwen Prompt Enhancer

Active plan:
- add Original / Official Qwen prompt mode to Telegram settings
- integrate T2I and I2I official Qwen 9B PE checkpoints
- keep enhancer on-demand so 24 GB GPU support remains possible
- fail open to original prompt if enhancement fails
- surface whether enhancement was used in the image result
- extend runtime tests and CI before merging


## 2026-09-24 — Smarter Vast offer discovery

Completed:
- Telegram still displays a compact maximum of 8 offers
- live discovery scans up to 64 candidates per query, while the Vast gateway requests an even wider backend slice for local ranking
- normal search queries 48 GB+ separately from the 24 GB+ fallback pool
- preferred and fallback candidates are deduplicated before ranking
- 48 GB+ offers rank ahead of lower-VRAM fallback cards
- added a dedicated “48GB+ only” search mode and mode-preserving refresh/back buttons
- overlapping marketplace requests are serialized
- added tests for search breadth, preferred-only mode, configuration and UI callbacks
