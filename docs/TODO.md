# TODO

## Current continuation

Active plan: `docs/DOWNLOAD_COST_PLAN.md`.
Branch: `fix/vast-download-cost-awareness`, based on the completed Codex branch `codex/vast-offer-machine-lookup`.

Completed:
- preserve the proven machine-scoped exact Offer ID recovery and lifecycle safety guards
- account for precise Download/Upload quotes; rank known offers using cold-download plus running-time estimates
- apply an optional download-rate ceiling in discovery and again before create; require confirmation on transfer-price changes
- disclose estimates/unknown rates before rent and distinguish the running-time counter from the invoice total
- stop unconditional enhancer prefetch; download only the explicitly requested enhancer
- compile check and full CI: 150 tests passed on implementation commit `04e4362676d21a2e4ae735456be7c2943cfdc2bf`, run `36202559680`

## Deployment — pending for the download-cost branch

- Verify the current state of `/opt/pixelpilot` and `pixelpilot.service`; preserve `.env`, SQLite and uncommitted work.
- Deploy this branch using `docs/RUNBOOK.md`, keeping the worker's `PIXELPILOT_REPO_REF` on the same published branch as the controller. Do not blindly reset to `main`.
- Confirm CI for the exact chosen deployment HEAD, restart the existing service and perform read-only preflight/offer checks.
- Refresh old offer cards so snapshots contain `machine_id` and transfer quotes; inspect real Download/Upload rates and the configured comparison assumptions in Telegram.
- Run one text-to-image and one edit smoke test when an authorized server/desktop session is available and the download-inclusive cost has been reviewed. No extra paid rental is needed merely to repeat the already-proven exact-ID fix.
- During any authorized trial, record the trial's Instance ID and delete only that Instance afterward, then verify provider and local state. Never touch a pre-existing unrelated Instance.

Historical completion, not a claim about this continuation: the Codex branch was deployed, rented Offer `45242185`, reached Qwen READY on Instance `52659808`, then destroyed that test Instance. Its $0.10310 local counter was an hourly-component estimate, not the $1.73 invoice shown later. A literal Telegram Desktop click and image-generation/edit validation were not established by that historical record. See `docs/PROGRESS.md`.

## Runtime follow-up

- Measure actual 24 GB and 48 GB generation latency, peak VRAM and cold-download volume before changing hardware thresholds or the 70 GB comparison assumption.
- Keep the comparison period explicit; setup time counts as billed time and long sessions can change which quote is cheaper.
- Consider an owner-selected Download ceiling if desired; unset allows known/unknown quotes with disclosure, while a configured ceiling excludes unknown rates. Zero means genuinely free download only.
- Reconcile a real ambiguous create only if one occurs; do not deliberately create another paid Instance to exercise that path.
- Optional seed-input UI remains a later enhancement.

No persona/chat/audio/video work is planned for the image product.
