# Active plan — Vast download cost awareness (2026-09-26)

Base: `codex/vast-offer-machine-lookup` at `d84c9e7e9c7dd0ef8c769efcc58c9de9517d0118`.
Matching push CI: `36198172864`, success. `main` is still `aad2cb6`; do not discard the seven recovered commits or merge unrelated branches.

## Evidence

- Prior Codex work recorded a live rent/READY/destroy cycle for Instance `52659808`; this session has verified that record and its matching CI, not repeated the live cycle.
- The owner's invoice for that Instance shows $1.61 download versus about $0.10 GPU. The prior $0.10310 controller estimate is running-time cost, not the Vast invoice total.
- Current discovery ranks VRAM and hourly price; normalized snapshots omit bandwidth rates. Both optional enhancer checkpoints are prefetched after startup even in Original mode.

## Implementation

1. Preserve the machine-scoped, exact Offer ID lookup and all lifecycle safety guards.
2. Preserve precise download/upload USD/GB rates in offer snapshots; show USD/TB with an explicit unit conversion and mark missing/invalid rates unknown, never free.
3. Compare a configurable cold-download allowance plus a configurable number of billed running hours. Keep this estimate distinct from the real invoice, with storage already included in `dph_total` and ongoing transfers excluded.
4. Add an optional download-rate ceiling, apply it to live discovery and before rent, and require fresh confirmation on bandwidth price changes.
5. Make optional enhancer downloads owner-requested rather than unconditional; never delay Original readiness. Retain raw prompts and fail-open enhancement behavior.
6. Add regression tests, run CI at the exact pushed HEAD, update memory/decisions/progress/runbook and report deployment separately.

## Completion gates

- [ ] Implementation and regression tests.
- [ ] Exact-HEAD full CI success.
- [ ] Updated project records and deployment handoff.
- [ ] Deploy controller and runtime ref together; real Telegram generation/edit verification only with authorized server/desktop access. Do not create a paid instance merely to re-prove the previously completed rental fix.

No new paid Vast instance has been created in this session. No server or Telegram Desktop connection is available through the currently connected tools.
