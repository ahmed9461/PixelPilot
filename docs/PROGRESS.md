# Progress

## Latest status — 2026-09-26, download-inclusive offer selection

Branch: `fix/vast-download-cost-awareness`. Plan: `docs/DOWNLOAD_COST_PLAN.md`.

- Continued from the actual Codex HEAD `d84c9e7e9c7dd0ef8c769efcc58c9de9517d0118` on `codex/vast-offer-machine-lookup`, not the earlier branch named in the interrupted prompt. Verified its matching CI `36198172864` was successful.
- Confirmed that prior project records already documented rent/READY/destroy for the same Instance `52659808` shown in the owner's invoice. This continuation did not repeat that live test or a Telegram Desktop click.
- The invoice shows `$1.61` download charges for 61.8 GB, around `$0.10` GPU and `$0.02` storage, with `$1.73` total. The displayed `$0.03/GB` is rounded. The earlier local `$0.10310` estimate was the hourly running-time component, not the final invoice. The invoice alone does not identify which downloaded component consumed each byte.
- Added precise inbound/outbound USD/GB fields to normalized offer snapshots, explicit USD/TB display using 1 TB = 1000 GB, and validation distinguishing genuinely free quotes from unknown/invalid/negative/non-finite rates.
- Discovery now ranks candidates by assumed cold-download cost plus billed hours. Defaults are 70 GB and one hour, both configurable and visibly described as assumptions. Allocated storage already included in `dph_total` is not added twice. The 48 GB+ only mode remains intact.
- Added optional `VAST_MAX_DOWNLOAD_USD_PER_TB` filtering in marketplace queries, local discovery and live pre-create validation. Unset adds no rate ceiling; zero accepts genuine free download only. A configured ceiling rejects unknown rates.
- Changes in either Download or Upload price require refreshed confirmation. Exact original Offer ID matching, the $0.50/hour limit, `cancel_unavail=true`, duplicate exclusion and ambiguous-create recovery remain preserved.
- Telegram now shows traffic quotes and comparison estimates before rental. Provision/status/deletion messages explicitly distinguish the running-time estimate from the total invoice and exclude transfer/stopped-storage charges.
- Removed unconditional prefetch of both optional enhancer checkpoints. Original startup starts neither download; an explicit enhanced request starts only its required T2I or I2I checkpoint, deduplicated per model. While uncached or on failure, that image uses Original; cached enhancement remains available.
- Full GitHub Actions CI on implementation/test commit `04e4362676d21a2e4ae735456be7c2943cfdc2bf`: run `36202559680`, job `108292131992`, **success**. Compile checks passed and `pytest -q` reported **150 passed in 5.51s**. Local pure pricing tests separately reported **15 passed**; the full suite ran in CI, not the local container.
- Updated project memory, decisions, plan, TODO, environment examples, README and runbook, replacing the stale unconditional prefetch/ranking guidance and unsafe reset-to-main deployment recipe.
- **Deployment remains pending for this branch.** No active authorized VPS/Telegram Desktop session was available through the connected tools. No new paid Instance was created or deleted. Next steps are safe controller/ref alignment, refreshed real quote inspection and a budget-reviewed generation/edit smoke test, not another rental just to repeat the earlier successful lifecycle proof.

The chronological entries below describe earlier states. The former 48-GB-first cost ordering and unconditional enhancer prefetch are superseded by the latest entry above.

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

Historical deployment note: the branch was ready for integration, but the persistent controller and GPU worker needed coordinated updates to avoid protocol mismatch.

## 2026-09-24 — Official Qwen Prompt Enhancer

Plan at that time:
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
- at this stage, 48 GB+ offers ranked ahead of lower-VRAM fallback cards
- added a dedicated “48GB+ only” search mode and mode-preserving refresh/back buttons
- overlapping marketplace requests are serialized
- added tests for search breadth, preferred-only mode, configuration and UI callbacks

## 2026-09-24 — Responsive server controls

Completed:
- moved long rent/provision and start/wait flows out of Telegram callback handlers into background tasks
- main server controls remain usable while provisioning or starting
- readiness probes use a short 5-second timeout instead of the long image-generation timeout
- Vast status reads are bounded to 8 seconds
- duplicate lifecycle tasks from rapid button presses are blocked
- stop/destroy cancel the waiting task only after a real Instance ID exists, preventing untracked paid instances
- stopped instances no longer get pushed back into a booting/error state by the readiness loop
- preflight no longer performs an unnecessary marketplace search
- repeated Telegram edits that produce “message is not modified” are treated as harmless no-ops
- offers above the final configured hourly ceiling are filtered locally
- added tests for bounded probes, stopped-state preservation, lifecycle task cancellation, repeated edits and final price filtering

## 2026-09-25 — Selective recovery of Vast and Qwen improvements

- Compared `main` with backup branch and PRs #18–21. The then-identified rental regression was exact-ID validation through a price-ranked truncated search pool: a valid selected ask could fall outside the result limit and appear unavailable. The later live comparison below identified the additional provider-side ID-filter mismatch.
- Restored the optional official Qwen T2I/I2I enhancer, expanded live offer discovery and responsive Telegram controls. Added exact-ID lookup without a ranked limit and policy/price/specification revalidation before creation.
- Kept the hard $0.50/hour cap and `cancel_unavail=true`; 24 GB CPU-offload search requires 48 GB host RAM, while full-GPU search has no unconditional host-RAM filter.
- Reserved lifecycle tasks before Telegram awaits, waited for in-flight Vast start mutations before manual stop/destroy, retried transient status timeouts, and blocked duplicate rent while an ambiguous create label remains. Status/startup can recover a matching Instance ID and its billing estimate.
- At this stage optional enhancer weights prefetched after image readiness. Original was the default; uncached or failed enhancement fell back to Original. Removed the fail-closed toggle.
- Added regression tests for exact ID, stale/change/policy, explicit rejection, 5xx/timeout/408/429 ambiguity, duplicate rent, rapid taps, start/stop ordering, provisioning retry, recovery and both prompt modes.
- Local full test suite: 104 passed. A live Vast smoke test was still pending; no paid instance was created during this stage.

## 2026-09-26 — Live rental follow-up

- The first deployment smoke test reported that Offer ID `21004761` was absent at exact-ID validation; no create request was sent for that selection. A refresh showed one new ID and one removed ID while two A6000 cards shared the same visible specifications.
- Updated exact-ID search to send a numeric ID in a structured Vast SDK query. The SDK string parser preserved `id=...` as text. This was a plausible mismatch, not proof from the screenshot that it caused the lookup failure.
- Added Offer IDs to Telegram cards and regression tests for numeric lookup and distinct same-spec asks. A read-only live query and real rental were still needed to confirm provider behavior.
- Local full test suite: 105 passed; no paid Vast instance was created in development.
- Commit `c1c2750` passed its matching CI. A subsequent live report said every displayed offer still failed, motivating the filter-parity check below.

## 2026-09-26 — Exact-ID filter parity follow-up

- Found that Vast SDK 1.6.0 seeds `rented=false` for structured searches, but not for string discovery searches. This was a real request mismatch, but the later live comparison proved it was not the remaining cause of the empty lookup.
- Exact lookup used numeric ID and explicit discovery defaults with `no_default=true`. Added SDK serialization coverage proving no extra `rented` filter. Local targeted tests: 47 passed.
- Full local suite: 106 passed. Live verification was still pending at this stage; no paid instance was created during the fix.
- The first matching CI exposed a timing-dependent status test assertion. It was changed to check the actual safety property: no overlapping Vast status calls during timeout recovery.

## 2026-09-26 — Live Vast Offer ID proof and machine-scoped revalidation

- Captured actual SDK request bodies and raw `/bundles/` responses without credentials. Discovery returned Offer ID `49299788` with `rented=false`, `machine_id=116779` and `allocated_storage=100`; an immediate same-storage numeric `id` lookup returned `offers: []`.
- This reproduced for multiple displayed IDs and integer, string, float and `in` forms. Querying `machine_id=116779` returned the original `49299788`, proving the offer had not disappeared and neither storage nor the removed default `rented` constraint explained the failure.
- Discovery now persists `machine_id`. Revalidation queries that machine with the same explicit baseline and `no_default=true`, accepting only the selected original Offer ID. A same-machine decoy cannot be rented.
- Added SDK serialization, same-machine exact matching, non-substitution and snapshot-persistence coverage. A read-only live pass found `49299788` with unchanged price/GPU/VRAM through the repaired path.
- The first live worker reached the gateway, where health exposed one stale `PE_FAIL_OPEN` reference. Health now reports the fixed fail-open policy directly, with a regression test.
- Local CI-equivalent checks passed: `compileall` and the full suite of 108 tests.
- Pushed `codex/vast-offer-machine-lookup`; matching CI runs succeeded for the offer repair and health follow-up.
- Deployed that branch on the controller, set the same `PIXELPILOT_REPO_REF`, restarted `pixelpilot.service`, and passed preflight including remote-ref reachability and eight live offers.
- The live lifecycle rented displayed Offer `45242185` without substitution, created Instance `52659808` at `$0.45556/hour`, and reached Qwen-Image READY on the same Instance after the health fix. Telegram Desktop/computer-control tools were not exposed, so the production `Orchestrator.rent_and_prepare` path was invoked directly; this was not a GUI click.
- Destroyed only test Instance `52659808`. Vast then reported no remaining Instances; SQLite returned to `phase=none`, and the inactive local running-time estimate was `$0.10310`. That estimate excluded transfer charges and was not the final provider invoice.
