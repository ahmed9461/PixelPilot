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

- Compared `main` with backup branch and PRs #18–21. The rental regression was exact-ID validation through a price-ranked truncated search pool: a still-valid selected ask fell outside the result limit and appeared unavailable.
- Restored the optional official Qwen T2I/I2I enhancer, expanded live offer discovery and responsive Telegram controls. Added exact-ID lookup without a ranked limit and policy/price/specification revalidation before creation.
- Kept the hard $0.50/hour cap and `cancel_unavail=true`; 24 GB CPU-offload search requires 48 GB host RAM, while full-GPU search has no unconditional host-RAM filter.
- Reserved lifecycle tasks before Telegram awaits, waited for in-flight Vast start mutations before manual stop/destroy, retried transient status timeouts, and blocked duplicate rent while an ambiguous create label remains. Status/startup can recover a matching Instance ID and its billing estimate.
- Optional enhancer weights prefetch after image readiness. Original is the default; uncached or failed enhancement falls back to the original prompt. Removed the fail-closed toggle.
- Added regression tests for exact ID, stale/change/policy, explicit rejection, 5xx/timeout/408/429 ambiguity, duplicate rent, rapid taps, start/stop ordering, provisioning retry, recovery and both prompt modes.
- Local full test suite: 104 passed. GPU rental and image runtime still require a live Vast smoke test; no paid instance was created during this work.

## 2026-09-26 — Live rental follow-up

- The first deployment smoke test reported that selected Offer ID `21004761` was absent at exact-ID validation; no create request was sent for that selection. A refresh showed one new ID and one removed ID while two A6000 cards shared the same visible specifications.
- Updated exact-ID search to send a numeric ID in a structured Vast SDK query. The SDK's string parser preserves `id=...` as text, whereas Vast documents the offer filter as a numeric ID. This is a plausible mismatch; the screenshot alone cannot establish that it caused the failed lookup.
- Added Offer IDs to Telegram offer cards and regression tests for numeric exact-ID query and visibly distinct same-spec asks. A read-only live exact-ID query and real rental are still needed to confirm the Vast-side result.
- Local full test suite after this follow-up: 105 passed; no paid Vast instance was created in development.
- The pushed commit `c1c2750` passed its matching GitHub Actions CI. A subsequent live report said every displayed offer failed exact-ID lookup, motivating the SDK default-filter parity check below.

## 2026-09-26 — Exact-ID filter parity follow-up

- Found that Vast SDK 1.6.0 seeds `rented=false` for structured searches, but not for string discovery searches. This was a real request mismatch, but the live comparison below proved it was not the remaining cause of the empty lookup.
- Exact lookup now uses a numeric ID and explicitly matches the discovery defaults with `no_default=true`. Added an SDK serialization regression test proving the request contains no extra `rented` filter. Local targeted tests: 47 passed.
- Full local suite after this follow-up: 106 passed. Live Vast search/rent after deploying this change is still pending; no paid instance was created during this fix.
- First matching CI run exposed a timing-dependent status-probe test assertion (it assumed only one total call even when the first had completed). The test now checks the safety property: no overlapping Vast status calls during timeout recovery.

## 2026-09-26 — Live Vast Offer ID proof and machine-scoped revalidation

- Captured the actual SDK request bodies and raw `/bundles/` responses without logging credentials. Discovery returned Offer ID `49299788` with `rented=false` and `machine_id=116779` using `allocated_storage=100`; the immediate structured lookup of the same numeric `id` and the same storage returned `offers: []`.
- The empty result reproduced for multiple currently displayed IDs and for integer, string, float and `in` forms of the `id` filter. Querying `machine_id=116779` returned the original `49299788` row, proving the offer had not disappeared and that neither storage nor the removed default `rented` constraint caused this failure.
- Discovery now persists `machine_id`. Revalidation queries that machine with the same explicit SDK baseline and `no_default=true`, then accepts only the exact selected Offer ID from the response. A same-machine decoy cannot be rented.
- Added SDK-serialization, same-machine exact-match, non-substitution and snapshot-persistence coverage. A read-only live pass re-found `49299788` with the same price/GPU/VRAM through the repaired path.
- The first live worker reached the gateway, where health exposed one stale `PE_FAIL_OPEN` reference left after fail-closed configuration was removed. Health now reports the fixed fail-open policy directly, with a regression test.
- Local CI-equivalent checks passed after both repairs: `compileall` succeeded and the full suite reported 108 passed.
- Pushed the independent branch `codex/vast-offer-machine-lookup`; matching GitHub Actions runs succeeded for both the offer fix and the health follow-up.
- Deployed the branch on the persistent controller, set `PIXELPILOT_REPO_REF` to the same published branch, restarted `pixelpilot.service`, and passed preflight including remote ref reachability and eight live offers.
- The live lifecycle path rented displayed Offer ID `45242185` without substitution, created Instance `52659808` at `$0.45556/hour`, and reached Qwen-Image READY on the same Instance after the health fix. The environment did not expose Telegram Desktop/computer-control tooling, so the same callback-owned `Orchestrator.rent_and_prepare` path was invoked directly rather than claiming a GUI click.
- Destroyed only test Instance `52659808`. Vast then reported no remaining Instances; SQLite returned to `phase=none`, and final billing was inactive at an estimated `$0.10310`.
