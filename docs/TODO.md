# TODO

## Deployment
- update the persistent controller to the merged Qwen-Image code
- identify and restart the actual controller service or process manager (see RUNBOOK)
- rent a fresh GPU from the Telegram UI
- validate first real Qwen-Image-2.1 download/load
- run one text-to-image and one edit smoke test
- verify one real exact-ID rental and ambiguous-error recovery with Vast without deliberately creating an extra paid instance

## Runtime follow-up
- record real 24 GB generation latency and peak VRAM
- record real 48 GB generation latency and peak VRAM
- adjust preferred offer ranking only if measurements show a better cost/performance threshold
- consider optional seed input UI after the basic deployment is proven

No persona/chat/audio/video work is planned for the image product.

## Plan — safe Vast improvements (2026-09-25)
1. Completed: restore selected image-studio enhancer/discovery/controls and fix exact-ID lookup and host-RAM filter.
2. Completed: guard duplicate rent and lifecycle races; reconcile ambiguous creates and retry transient status timeouts.
3. Completed local tests and documentation. Confirm CI on the pushed commit before merge; a real Vast rental remains a deployment smoke test.

## Live rental follow-up (2026-09-26)
1. Completed: reviewed live symptom and confirmed the SDK string parser preserves the numeric-looking ID as text.
2. Completed: send an integer ID filter through the Vast SDK and show Offer IDs on cards; retain exact-ID validation and no automatic substitute.
3. Completed: added regression tests, ran the full suite (105 passed), and confirmed CI on pushed commit `c1c2750`. Live rental initially still failed on all displayed asks; the filter-parity follow-up below addresses a further SDK mismatch.

## Exact-ID SDK filter parity (2026-09-26)
1. Completed: confirmed structured queries add `rented=false` by default while discovery's string query does not.
2. Completed: use the discovery baseline during exact-ID verification without the extra `rented=false`; retain the numeric ID and all post-lookup policy checks.
3. Superseded: the live request comparison showed that removing `rented=false` was necessary request parity but did not fix Vast's empty `id` filter result.

## Machine-scoped exact Offer ID recovery (2026-09-26)
1. Completed: captured discovery and validation request bodies and raw responses for the same live Offer ID `49299788` with the same 100 GB allocation.
2. Completed: persist the discovery `machine_id`, query that host during validation, and locally require the unchanged original Offer ID; never substitute another ask.
3. In progress: local full suite passed (108 tests, including the live-discovered health regression); push the updated independent repair branch, confirm matching CI, finish readiness on the existing test Instance, then destroy only that Instance.
