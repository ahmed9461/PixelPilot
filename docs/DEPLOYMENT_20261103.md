# New-VPS multimodal deployment

This repair follows merged PR #23 (`af65e4b`). The existing deployment is
`/opt/pixelpilot`, systemd `pixelpilot.service`, with its own `.venv`, `.env`
and SQLite database. Never replace the installation or its credentials.

## Behavior and limits

- Owner-only chat and vision: `Qwen/Qwen3.5-9B`, using the official
  `Qwen3_5ForConditionalGeneration` plus `AutoProcessor` classes.
- Text memory is keyed by owner ID in SQLite, survives service restart and is
  cleared by `/clear`. Eight recent turns are retained; outgoing context is
  bounded to 12,000 history characters and exactly 8,192 input tokens on the
  worker. Whole oldest turns are removed, never partial image-token sequences.
- At most three vision images; default visual budget is 1,048,576 pixels per
  image. Telegram photo and original image-document albums are supported.
  A photo means understanding by default; `/edit` or Edit mode selects editing.
- Image generation/editing uses `QwenImage21Pipeline`, PNG including returned
  alpha, original aspect/quality/steps settings, and up to ten references.
  Local edits are model-guided and do not promise exact unchanged pixels.
- Startup loads chat first. Images load on first request. Both controller and
  worker serialize GPU operations and release the previous model before loading
  another. Cancellation keeps the worker lock until its CUDA thread finishes.
- Image OOM discards the failed pipeline, preserving disk cache for retry.
  Offload hooks are reinstalled after optional enhancement to avoid stale
  CPU/CUDA placement. Actual GPU/OOM behavior still needs a paid GPU trial.

## Marketplace policy

Search sequential network stages, each scanning 80/48/32/24 GB pools (restricted
appropriately for dedicated 48/80 menus): 3000/1000, 2000/1000, 1000/500 Mbps.
Each query inspects up to `VAST_SEARCH_POOL_LIMIT=100` rows, ordered by download
speed, then deduplicates exact Offer IDs and validates locally. Premium queries
can be empty without hiding lower tiers. Only when no eligible offer exists,
slower offers appear separately without rental buttons; they cannot pass rental
validation. Do not automatically relax the minimum network policy.

The hard rental ceiling is **$0.60/hour**, validated by settings, query builder,
discovery, detail view and exact-ID live pre-create checks. A confirmation carries
the reviewed quote fingerprint; refreshing another card cannot silently change
an old confirmation. Preserve unique labels, `cancel_unavail=true`, pending
state and ambiguous-result reconciliation. Never substitute another offer.

Ranking gives download 32 points, upload 12, DLPerf 26, VRAM 14, reliability 11,
hourly value 10; small architecture/FLOPs/memory-bandwidth and datacenter bonuses
and transfer-cost penalties refine it. These are relative heuristics using
published data, not measured performance guarantees or a globally best offer.
BF16 requires Ampere or later CUDA compute capability, with NVIDIA/amd64 queries.
24/32 GB profiles require host RAM for offload; direct ports and disk are checked.
Reported VRAM is the provider's available memory, which can differ from nominal
product VRAM. Never assume the name alone verifies actual hardware.

The official Vast SDK documents `inet_down`/`inet_up` as **Mb/s (Mbps)**; the
API web page currently contains an inconsistent MB/s label. No factor of eight
is applied to SDK data. Native transfer rates are USD/GB, displayed as USD per
1000 GB. `dph_total` includes allocated disk; transfer and stopped storage are
additional. A free network quote is distinct from an unknown quote.

## Downloading and readiness

Official Hub `snapshot_download`, automatic `hf_xet`, four download workers,
persistent `/workspace/hf-cache`, partial-download resume and a free-space check
are used. Both model snapshots total about 52.5 decimal GB at verification;
the default 100GB disk also accommodates runtime and cache overhead. Optional
enhancers download only after explicit selection and require more disk/transfer.
No cache is deleted during switching. Bootstrap preserves old runtime venvs.

Authenticated health remains available during warmup. It reports phase/model,
known total bytes, cache growth in bytes/Mbps and percentage when metadata exists,
VRAM loading and loaded capabilities. Cache growth is an approximation of file
transfer, not a wire-level speed test. `/v1/models` lists **loaded** models only.
The initial ready message refers to chat/vision; image readiness is separate.

Worker packages: Transformers 5.22.1, Diffusers 0.42.1, CUDA PyTorch >=2.4 from
the Vast image. Source imports and dependency resolution can be checked on CPU;
that does not prove CUDA compatibility, model loading or numerical outputs.
New GPU architectures may require a newer CUDA-enabled PyTorch wheel/image.

## Transport, secrets and recovery

New rentals require verified HTTPS. The controller issues a unique TLS certificate
and private key for that worker, stores only the public trust certificate in
SQLite and sends key material through Vast's HTTPS configuration API. Bootstrap
refuses a public plaintext gateway. The controller trusts only its issued
certificate, rather than disabling certificate verification. No existing token
or API key is rotated. `VAST_API_KEY` never reaches the worker.

Keep root-private DB/env/backups and systemd `UMask=0077`. Existing image bytes
stay ephemeral. Chat history is private local text, not encrypted at rest; root
and anyone with a root-readable backup can read it. Protect those backups.

`PIXELPILOT_REPO_REF=main` remains the configured branch.
`PIXELPILOT_WORKER_COMMIT` can pin the full reviewed repair SHA while its PR is
pending merge. Bootstrap fetches that SHA and checks it out without hard reset.
After merge, retain a tested pin or update deliberately to a newly verified SHA.

Before deployment, back up tracked/untracked project files, `.env`, service unit,
pip freeze and a consistent SQLite backup with its API. Keep old venvs. Restart
only PixelPilot, check active/enabled/no restart loop and compare other running
services. Do not reboot the entire VPS just to prove the unit is enabled.
If rollback is needed, stop only PixelPilot; preserve the failed tree/current DB;
restore the previous Git ref and env/unit from the named private backup, rebind
the editable install and restart. SQLite changes here are backward compatible;
do not overwrite newer user data with an old snapshot automatically.

No GPU is rented as part of code or marketplace testing. A real trial needs the
owner's approval of a specific live offer, with its rate and transfer charges.

## Official references

- https://huggingface.co/docs/transformers/main/en/model_doc/qwen3_5
- https://huggingface.co/Qwen/Qwen-Image-2.1
- https://huggingface.co/docs/diffusers/main/en/api/pipelines/qwenimage21
- https://huggingface.co/docs/huggingface_hub/guides/download
- https://github.com/vast-ai/vast-python (SDK offer field documentation)
- https://docs.vast.ai/api-reference/search/search-offers
