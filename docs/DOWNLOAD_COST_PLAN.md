# Vast download cost awareness — implementation complete, deployment pending

Date: 2026-09-26.
Status: completed and merged to `main` via PR #22.
Base: `codex/vast-offer-machine-lookup` at `d84c9e7e9c7dd0ef8c769efcc58c9de9517d0118`; its matching CI `36198172864` succeeded.

## Evidence and scope

- Prior Codex work recorded a successful rent/READY/destroy cycle for Instance `52659808`. This continuation verified that record and matching CI; it did not repeat the paid trial or a Telegram Desktop click.
- The owner's invoice for that Instance shows $1.61 for downloading 61.8 GB versus about $0.10 GPU and $0.02 storage. The displayed $0.03/GB is rounded; it must not replace the precise API quote. The earlier $0.10310 controller figure was a running-time estimate, not the invoice total.
- Before this change, discovery ranked VRAM/hourly price and snapshots dropped transfer rates. Startup also prefetched both optional enhancer checkpoints, including in Original mode. The invoice does not identify how many bytes came from each component.

## Completed implementation

1. Preserve machine-scoped lookup with exact original Offer ID matching and all lifecycle protections: $0.50/hour cap, `cancel_unavail=true`, duplicate exclusion and ambiguous-create reconciliation.
2. Preserve precise inbound/outbound USD/GB rates in public snapshots. Display USD/TB using an explicit 1 TB = 1000 GB convention. Missing, malformed, negative or non-finite rates are unknown, never free; genuine zero remains zero.
3. Rank discovered candidates by a configurable cold-download allowance plus billed running hours. Defaults are 70 GB and 1 hour, comparison assumptions rather than a measured model size or a final-invoice guarantee. `dph_total` already includes allocated storage.
4. Add an optional download-rate ceiling to discovery and live pre-create validation. Changes in either inbound or outbound rates require refreshed confirmation. No arbitrary new rate ceiling is imposed by default.
5. Download only the optional T2I or I2I enhancer needed by an explicit enhanced request. Original readiness starts neither optional download. While the requested checkpoint is downloading, that image falls back to Original; cached enhancement retains fail-open behavior.
6. Show traffic quotes and estimates before confirmation; label the running-time meter as excluding transfers and stopped-instance storage.
7. Update memory, progress, decisions, environment examples, README and deployment instructions.

## Validation

- Implementation/test commit: `04e4362676d21a2e4ae735456be7c2943cfdc2bf`.
- Matching GitHub Actions run: `36202559680`, job `108292131992`: **success**.
- `python -m compileall -q src scripts`: passed.
- Full `pytest -q`: **150 passed in 5.51s** on GitHub Actions.
- Local pure pricing tests: **15 passed**; the complete dependency environment was supplied by CI, not the local container.
- New coverage includes precision and units, zero/unknown/invalid rates, ranking, query/local caps, live down/up quote changes, same-ID single creation, Telegram disclosure, runtime-only billing labels, no Original prefetch, per-model download deduplication, caching/fallback and shutdown cleanup.

## Completion gates

- [x] Implementation and regression tests.
- [x] Full CI success for the exact implementation HEAD above.
- [x] Updated project records and deployment handoff.
- [ ] Deploy the controller and matching runtime branch on `/opt/pixelpilot`; verify `pixelpilot.service` and `PIXELPILOT_REPO_REF`.
- [ ] Inspect refreshed real quotes and perform a budget-approved Telegram generation/edit smoke test with server/desktop access. Do not rent merely to re-prove the completed earlier rental fix.

No additional paid Vast instance was created by the repository continuation itself. The owner later deployed the validated build, confirmed the live bot behavior was working correctly, and approved promotion to `main`. PR #22 is the integration point; future deployments should follow `docs/RUNBOOK.md` and keep controller/worker refs aligned to `main`.
