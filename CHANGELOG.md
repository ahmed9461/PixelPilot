# Changelog

## 0.2.0 — 2026-09-13

- Completed Vast search/rent/start/stop/destroy orchestration.
- Corrected Vast template handling to `template_hash`.
- Added per-instance Worker token and Vast Caddy/Portal proxy profile.
- Added full FLUX.1 Krea model downloader and API workflow.
- Added Worker generation endpoints and controller WorkerClient.
- Added Telegram generation wizard, ratios, batch, seeds, originals, reruns.
- Added provisioning rollback, recovery, preflight, and cost guard.
- Expanded automated tests to 18.

## 0.3.0 - 2026-09-14

- Added secure interactive `.env` configuration helper; secret values are not echoed.
- Hardened Vast lifecycle/reconciliation and provisioning recovery.
- Expanded preflight and offer validation.
- Added lifecycle/preflight/security tests; local suite is now 31/31 passing.
- Updated project memory/runbook for first live acceptance.
