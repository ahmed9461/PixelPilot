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
