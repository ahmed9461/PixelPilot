# Decisions

## 2026-09-26 — Download-inclusive costs and requested-only optional downloads

This decision supersedes the older VRAM-first price ranking and startup enhancer-prefetch policy below; the image product and lifecycle safety requirements remain unchanged.

### Precise quotes and units

Persist inbound/outbound quotes from native `inet_down_cost` / `inet_up_cost` as USD/GB, without rounding before computation. USD/TB display explicitly uses `1 TB = 1000 GB`; supported per-TB aliases are converted back to USD/GB only when the native field is absent. A present but invalid native value is unknown, not overridden by an alias. Missing, invalid, negative and non-finite values never become free; genuine zero remains zero.

### Selection and disclosure

Rank the discovered candidate pool using `dph_total × billed hours + inbound USD/GB × assumed cold-download GB`. Defaults are one billed hour and 70 GB, configurable via `VAST_COST_COMPARISON_HOURS` and `VAST_ESTIMATED_DOWNLOAD_GB`. They are comparison assumptions, not a measured filesize, setup-time prediction or final-invoice guarantee. Billed time includes setup, and actual setup/session duration may exceed the chosen period.

Allocated disk is already included in `dph_total` and must not be double-counted. Upload, optional enhancer downloads, additional traffic/retries and stopped-instance storage can add costs. Known quotes rank before unknown quotes; 48 GB+ is an equal-cost tie-breaker, not an unconditional cost preference. The dedicated 48 GB+ view remains available. Do not claim a global marketplace optimum beyond the discovered pool.

Display transfer quotes and the comparison before rental confirmation. A changed Download or Upload quote requires a new confirmation even when hourly price is unchanged. Label the running-time counter honestly, including after deletion: it does not meter traffic or the final invoice. The owner's $1.61 download charge versus roughly $0.10 GPU on Instance `52659808` motivates this separation; the invoice alone does not attribute bytes to specific checkpoints.

### Optional ceiling, not an invented spending budget

`VAST_MAX_DOWNLOAD_USD_PER_TB` is unset by default. When explicitly configured, apply it to the query, local candidate filtering and live pre-create validation; unknown rates are then rejected. Zero permits free download only. The hard $0.50/hour ceiling and all existing guards remain intact. A rate ceiling is not a total-spend ceiling, and this change does not impose an arbitrary additional budget.

### Download only the requested enhancer

Original startup and Original requests must not start either optional checkpoint download. The first explicit enhanced request starts only its necessary T2I or I2I checkpoint, with at most one in-flight download task per model. That image uses Original while uncached; later images may use the cached enhancer. Checkpoint failure leaves the model uncached and enhancement fails open. Health reports download/cached state and fixed `fail_open=true`.

This removes hidden optional cold-start traffic while preserving the official enhancement capability. It does not claim that the base image model is free to download or that all historical invoice bytes came from enhancers. Shutdown cleans asynchronous task state; cancelling a wrapper task is not proof that its underlying download thread or provider billing stopped immediately.

### Deployment boundary

Repository pushes, CI and a historical live trial are distinct evidence. Deploy the controller and worker ref together from the verified branch/tag; do not reset to an older `main`. The current continuation has no new authorized VPS/Desktop session and therefore makes no new deployment, GUI or paid-instance claims. Implementation and regression tests passed full CI at `04e4362676d21a2e4ae735456be7c2943cfdc2bf` (150 tests, run `36202559680`).

## 2026-09-24 — Qwen-Image-2.1 pivot

PixelPilot is an image studio rather than a multimodal chat assistant.

### Model and prompts

Use `Qwen/Qwen-Image-2.1` through the official Diffusers pipeline family. Original mode passes the user's prompt unchanged after non-empty validation. Do not apply assistant personality, emotion, tone, language, reasoning or chat context. Optional Qwen Enhance is selected explicitly.

### GPU policy

Minimum searchable VRAM is 24 GB; preferred execution tier is 48 GB+. In automatic mode, 24–47 GB uses CPU offload and 48 GB+ uses full-GPU placement. VAE tiling/slicing are enabled, BF16 is the default, the hourly cap is $0.50 and default disk is 100 GB.

### Quality, editing and output

Standard uses approximately 1K-class dimensions for lower VRAM/latency. 2K uses the model-card aspect-ratio sizes. Default steps remain 40. Support a single reference and Telegram albums up to 10 images. Use PNG to preserve quality and alpha/transparency when produced.

Remove vLLM, Whisper, Qwen3-VL, audio/video understanding, assistant profiles, chat history and text-response streaming from active code.

## 2026-09-24 — Optional official Qwen Prompt Enhancer

Modes: `original` preserves the user prompt; `qwen` requests official rewriting. Use the official 9B checkpoints `Qwen/Qwen-Image-2.1-PE-T2I` and `Qwen/Qwen-Image-2.1-PE-I2I`.

The PE model must not stay resident beside diffusion. Temporarily free/move the diffusion pipeline, load the necessary PE model on CUDA, rewrite once with the checkpoint's `system_prompt.txt`, unload it, clear CUDA, restore diffusion placement, then generate. This preserves the 24 GB profile at the cost of extra latency. Original remains default. The no-extra-optional-download intent is implemented by the requested-only policy above, replacing the intermediate startup-prefetch behavior.

### Official enhancer inference profile

The Transformers path follows Qwen's published `prompt_rewrite/run_transformers.py` contract:
- both paths use `AutoProcessor` and `AutoModelForImageTextToText`
- T2I uses presence penalty 1.5 and `max_new_tokens=16256`
- edit uses presence penalty 0 and `max_new_tokens=24000`
- both use temperature 1.0, top-p 0.95, top-k 20, thinking enabled and seed 42
- edit references are capped to about one megapixel before rewriting
- CPU-offload search requires 48 GB host RAM; full-GPU search has no unconditional host-RAM floor. Enhancement may need more RAM and falls back to Original on failure.

## 2026-09-25 — Offer ID and lifecycle safety

- Query the live marketplace before rental rather than trusting a ranked cached pool. The original `id` filter approach was later superseded by machine-scoped proof below; exact original Offer ID matching remains mandatory.
- Require confirmation on changed hourly price/GPU/VRAM; transfer-quote changes are now included by the current decision above.
- Preserve `cancel_unavail=true`. Explicit rejection may clear pending state; timeouts, 408/429 and 5xx retain the unique label and block another rent until recovery.
- Reserve Telegram lifecycle tasks before awaits, serialize manual stop/destroy after in-flight starts, and retry isolated status timeouts during provisioning.
- The intermediate choice to prefetch PE weights after readiness is superseded. Original fallback for uncached/failed enhancement remains required.

## 2026-09-26 — Live offer identification

- Keep exact original ID matching before rent. Passing `id` as an integer was plausible but later live evidence showed the provider filter itself returned no match for discoverable IDs.
- Show Offer ID on every Telegram card. Identical model, price and reliability may represent different asks; compare IDs and quote details on refresh.
- A screenshot alone could not prove provider removal or a string-type mismatch. Read-only request/response evidence was required.

## 2026-09-26 — Match SDK search defaults on validation

The installed SDK structured search adds `rented=false` while string discovery does not. Use explicit `verified=true`, `external=false`, `rentable=true` and `no_default=true` so verification does not silently add a different constraint. Retain local price/specification/policy checks and `cancel_unavail=true`. Removing the extra constraint did not by itself repair the provider's empty `id` result.

## 2026-09-26 — Revalidate through the discovery machine

Live `/bundles/` evidence returned `49299788` during discovery, then an empty `id=49299788` lookup across numeric/string representations with the same 100 GB allocation. A query constrained by discovery `machine_id` returned that original ask.

Persist numeric `machine_id` to bound raw lookup results, then require the exact original Offer ID. Never accept another offer on that machine. Keep explicit baseline filters with `no_default=true`, the hard hourly limit, all policy/specification checks, cancellation-on-unavailable behavior, duplicate exclusion and ambiguous-create reconciliation.
