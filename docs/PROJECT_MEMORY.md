# PixelPilot — Project Memory

## Current goal

PixelPilot is an owner-only Telegram image studio backed by temporary Vast.ai GPUs.

Active model: `Qwen/Qwen-Image-2.1`.

Supported flows: text-to-image, single-image editing and multi-reference editing with Telegram albums, up to 10 reference images. Output is PNG with seed and dimensions shown to the owner.

Current stable baseline: `main`. PR #22 merged the validated Vast rental recovery and download-cost-aware work from `fix/vast-download-cost-awareness`. The owner deployed the pre-merge build and reported the live bot working correctly. Future work should branch from current `main`, and controller/worker refs must remain aligned when deploying.

## Non-negotiable behavior

1. No assistant personality, emotion, tone, role or chat-style profile is part of image generation.
2. Original mode sends the user's prompt unchanged.
3. Official Qwen Prompt Enhancer is an explicit owner-controlled mode, never a hidden layer. Use only the configured official T2I/I2I models and their shipped `system_prompt.txt`.
4. Do not maintain conversational context or chat history. Each image request is independent.
5. User-facing controls are aspect ratio, resolution quality, inference steps and prompt mode.
6. Support up to 10 user-supplied reference images.
7. Preserve PNG output so alpha/transparency is not destroyed.
8. Keep generated/reference image bytes ephemeral; do not persist them in SQLite.
9. Keep Vast lifecycle owner-controlled; automatic deletion is opt-in.
10. `VAST_API_KEY` stays on the controller.
11. The hard rental ceiling remains `$0.50/hour`; it is not an all-in invoice ceiling.
12. Every offer refresh queries the live marketplace.
13. The running-time estimate is separate from transfer charges and stopped-instance storage. Never label it the total/final Vast invoice.
14. The public runtime port is an authenticated PixelPilot image gateway.
15. Load Qwen-Image directly with Diffusers. Do not restore vLLM, Whisper or chat-completions runtime.
16. Preserve the exact selected Offer ID, `cancel_unavail=true`, duplicate-rent guards and ambiguous-create reconciliation. Never substitute a similar offer automatically.

## Hardware policy

- Search minimum: 24 GB VRAM; preferred execution tier: 48 GB+.
- Default disk: 100 GB. Optional enhancer checkpoints download only after an explicit enhanced request; monitor free space if both caches are eventually used.
- Minimum host RAM filter: 48 GB for CPU-offload offers; no unconditional host-RAM floor on full-GPU offers. More RAM may help Qwen Enhance.
- 24–47 GB VRAM: automatic CPU model offload with VAE tiling/slicing.
- 48 GB+: automatic full-GPU placement.
- Default dtype: BF16. Default steps: 40.

The BF16 checkpoint components are roughly 33 GB before runtime overhead, so 24 GB requires offload while 48 GB-class GPUs are the practical full-GPU target. Hardware preference is not a guarantee that an offer has the lowest total cost.

## Image settings

Standard sizes:
- 1:1 — 1024×1024
- 4:3 — 1152×896
- 3:4 — 896×1152
- 3:2 — 1216×832
- 2:3 — 832×1216
- 16:9 — 1344×768
- 9:16 — 768×1344

2K sizes:
- 1:1 — 2048×2048
- 4:3 — 2400×1792
- 3:4 — 1792×2400
- 3:2 — 2528×1696
- 2:3 — 1696×2528
- 16:9 — 2752×1536
- 9:16 — 1536×2752

## Architecture

```text
Telegram owner
  -> PixelPilot Controller
     -> image settings + lifecycle + running-time estimate in SQLite
     -> live Vast offer discovery / transfer-aware comparison
     -> authenticated Vast gateway :8190
        -> QwenImage21Pipeline
           -> CUDA GPU
           -> optional CPU offload when VRAM < 48 GB
        -> explicitly requested official Qwen 9B prompt enhancer
           -> download only the needed checkpoint
           -> load for one rewrite, release before diffusion
```

## Persistence

SQLite stores lifecycle state, latest offer snapshots and refresh metadata, running-time/cost-guard state, image UI settings and operational metadata events. Offer snapshots include exact Offer ID, `machine_id` and precise download/upload quotes, but are never a substitute for the live rent check. SQLite does not store generated/reference image bytes, chat history or prompt bodies.

## Removed from active project

Qwen3-VL, Qwen2.5-Omni, Whisper, vLLM, audio/video understanding, assistant personalities, emotion/tone/reasoning/language profiles, custom chat prompts, chat context/history and response streaming remain removed.

## Official prompt enhancer

- Mode is stored in SQLite and defaults to `original`; it sends the prompt unchanged.
- `qwen` requests official enhancement before generation when the selected checkpoint is cached.
- T2I: `Qwen/Qwen-Image-2.1-PE-T2I`.
- I2I: `Qwen/Qwen-Image-2.1-PE-I2I`.
- Startup and Original requests download neither optional checkpoint. The first explicit enhanced request starts only its needed T2I or I2I download, with one in-flight task per model. While uncached, that image uses Original and reports fallback. Later requests can use the cached enhancer.
- The enhancer loads for one rewrite and releases CUDA before diffusion. Failures always fall back to Original.
- Optional downloads can add transfer charges beyond the comparison allowance. Do not prefetch both models merely to report READY or pass a health check.
- Authenticated health reports `fail_open=true`, `download_policy`, downloading models and cached models.

## Vast offer discovery and transfer costs

- Telegram displays at most the best 8 discovered candidates. Discovery scans a wider live pool, with dedicated 48 GB+ and 24 GB+ fallback queries, then deduplicates.
- Rank known quotes by `hourly dph_total × comparison hours + inbound USD/GB × assumed download GB`. Defaults: `VAST_COST_COMPARISON_HOURS=1`, `VAST_ESTIMATED_DOWNLOAD_GB=70`. These are editable comparison assumptions, not measured usage or a final bill. The billed period includes setup time; actual usage can be longer.
- `dph_total` already includes the requested disk. Do not add allocated storage twice. Upload, extra downloads, retries and stopped-instance storage are not part of this simple comparison.
- Native `inet_down_cost` / `inet_up_cost` are preserved as precise USD/GB quotes. Display USD/TB using the explicit decimal convention `1 TB = 1000 GB`. Do not round before calculating.
- Missing, malformed, negative or non-finite rates are unknown, never zero. Genuine zero is free. Known quotes rank before unknown quotes; 48 GB+ is a tie-breaker among equal known costs. Among unknown quotes, retain hardware/hourly ordering.
- An owner-controlled “48 GB+ only” search remains available. Do not promise the globally cheapest server beyond the discovered candidate pool.
- `VAST_MAX_DOWNLOAD_USD_PER_TB` is optional and unset by default. A configured ceiling is applied to marketplace discovery, local filtering and live pre-create validation; unknown rates then fail closed. Zero accepts free inbound quotes only. It is a rate ceiling, not a total-spend cap.
- Offer cards show the actual Offer ID and Download $/TB. Details show both transfer directions and the assumed cold-start comparison before confirmation. A changed download or upload quote requires a refresh and new confirmation, as do changed hourly price/GPU/VRAM.
- Discovery snapshots retain `machine_id`. Vast's live `/bundles/` `id` filter was observed not matching returned Offer IDs. Revalidation narrows by the snapshot's machine and accepts only the exact original Offer ID from raw rows; a different ask on the same host is never substituted.
- Revalidation uses explicit `verified=true`, `external=false`, `rentable=true`, `no_default=true` and the same allocated storage, avoiding the SDK's extra default `rented=false` constraint.
- Explicit 4xx rejection can clear pending state; network, 408/429 and 5xx outcomes retain the unique label and block another rent until reconciliation.
- Serialize rapid refreshes; do not rotate cached results to simulate market changes. Refresh legacy snapshots after deployment to obtain machine IDs and transfer quotes.

## Telegram server-control responsiveness

- Long Vast lifecycle waits never occupy a Telegram callback handler. Rent/provision and start/wait run as named background tasks.
- Status uses a short probe timeout and remains available during booting/provisioning, as do safe stop/destroy controls.
- Reserve the lifecycle task before any callback await; prevent duplicate tasks from rapid clicks.
- Wait for in-flight Vast start mutations before stop/destroy. Retry isolated status timeouts within the overall readiness deadline.

## Evidence and deployment boundary

Prior Codex work recorded Offer `45242185` → Instance `52659808` → Qwen READY → deletion of that test Instance. Its local `$0.10310` figure was a running-time estimate, not the owner's later invoice containing `$1.61` download fees. Implementation commit `04e4362676d21a2e4ae735456be7c2943cfdc2bf` passed compile checks and all 150 tests in CI run `36202559680`; head `5bc7cec7574f92b7c9980734cb6b6ff9f793c44d` also passed CI before merge. The owner subsequently deployed the build, verified the live bot behavior, and approved promotion to `main` via PR #22.
