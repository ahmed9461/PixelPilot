# Test Plan

## CI

Every push and pull request runs:
- editable controller install
- `python -m compileall -q src scripts`
- `pytest -q`

## Required coverage

- Qwen-Image defaults and validation
- 24 GB minimum / 48 GB preferred GPU policy
- Vast query and lifecycle
- machine-scoped exact Offer ID lookup with SDK request parity and no same-host substitution, changed price/GPU/VRAM, hard cap, rejection and ambiguous create reconciliation
- duplicate rent and rapid callback handling, start/stop ordering, retry of transient status timeouts
- image generation API payloads
- exact prompt preservation
- optional official T2I/I2I enhancement and fallback to Original when uncached or failed
- multi-reference multipart edits
- image settings/preset dimensions
- owner-only access helpers
- billing and cost guard
- server recovery
- Telegram image-focused copy
- absence of retired chat/persona runtime dependencies

## Deployment smoke test

After controller deployment and renting a GPU:
1. health reaches READY
2. text-to-image returns PNG
3. single-image edit returns PNG
4. two-image album edit works
5. Standard and 2K preset switching works
6. stop/start restores readiness
7. destroy finalizes billing state
