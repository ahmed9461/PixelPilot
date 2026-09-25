# Runbook

## Current deployment target

This continuation lives on `fix/vast-download-cost-awareness`, based on the completed rental repair in `codex/vast-offer-machine-lookup`. The owner identified the persistent controller as `/opt/pixelpilot` and its service as `pixelpilot.service`; verify these locally before changing anything.

Repository work and CI are complete. This continuation did **not** deploy the VPS or access Telegram Desktop. A prior Codex deployment/rental is historical evidence, not confirmation that this new branch is already running.

## Safe controller update

Use an authorized SSH session, such as the owner's configured `New-VPS` access. Inspect the working tree and current service without dumping `.env` or credentials. Preserve SQLite, `.env` and any uncommitted work. Do not use `git reset --hard origin/main`: `main` may still predate the fixes.

```bash
cd /opt/pixelpilot
git status --short
git branch --show-current
git rev-parse HEAD
git fetch origin fix/vast-download-cost-awareness
```

Stop and reconcile any local modifications rather than discarding them. For a clean clone, use the appropriate branch path:

```bash
# First checkout only, if this local branch does not already exist:
git switch --track origin/fix/vast-download-cost-awareness
# For an existing local branch instead:
# git switch fix/vast-download-cost-awareness
# git pull --ff-only origin fix/vast-download-cost-awareness

git rev-parse HEAD
git rev-parse origin/fix/vast-download-cost-awareness
```

Confirm both SHAs agree and GitHub Actions succeeded for that exact SHA, not an older green run. The implementation/test commit `04e4362676d21a2e4ae735456be7c2943cfdc2bf` passed all 150 tests in run `36202559680`; later documentation commits also need their matching CI checked.

Using the existing controller environment, edit only the intended nonsecret `.env` settings. Do not replace the whole file with `.env.example` on an existing installation:

```dotenv
PIXELPILOT_REPO_REF=fix/vast-download-cost-awareness
VAST_ESTIMATED_DOWNLOAD_GB=70
VAST_COST_COMPARISON_HOURS=1
```

The worker bootstrap currently uses `git clone --branch`: use the matching published branch or tag, not an arbitrary commit SHA as `PIXELPILOT_REPO_REF`. When integrating into another branch later, update controller and worker ref together. Existing workers do not become upgraded merely because this environment variable changes.

The optional rate ceiling is absent by default. For example, an owner-selected ceiling of $5 per 1000 GB is `VAST_MAX_DOWNLOAD_USD_PER_TB=5`; zero accepts genuinely free inbound quotes only. Leave the key absent/commented for no ceiling, not empty. Do not impose a different budget without the owner's choice. A configured ceiling excludes unknown rates and is not an all-in spending cap.

Use the Python environment already configured for the service:

```bash
source .venv/bin/activate
pip install -e .
python scripts/preflight.py
sudo systemctl restart pixelpilot.service
sudo systemctl is-active pixelpilot.service
```

Verify process startup and only the needed nonsecret configuration fields. Do not print tokens or entire environment files. Refresh Telegram offers after deployment; old snapshots lack machine IDs or transfer rates. Inspect a real offer's Download/Upload quotes, allocated-disk hourly price and estimated comparison before any paid confirmation.

## Cost interpretation

- The comparison is `billed hours × dph_total + assumed download GB × precise inbound USD/GB`.
- Defaults are 70 GB and one billed hour. The size is an allowance, not a measured model filesize; the period includes setup, and actual setup/session duration may exceed it.
- `dph_total` already includes allocated disk: no double-added storage.
- Display conversion is explicitly `1 TB = 1000 GB`. Native `inet_down_cost` and `inet_up_cost` are USD/GB; use their full precision rather than rounded invoice/console text.
- Missing/invalid rates are unknown, not free. Known estimated costs rank first; the 48 GB+ only view remains available.
- Uploads, optional enhancer downloads, additional transfers/retries and storage while stopped can add charges. The running-time counter shown during provision/status/deletion does not meter those charges and must not be called the final invoice.
- Historical example: Instance `52659808` had a local hourly-component estimate of `$0.10310`, but the owner's invoice later showed `$1.61` of downloads and `$1.73` total. The invoice does not identify a byte breakdown by downloaded component.

## Preflight and GPU profiles

`python scripts/preflight.py` checks configured credentials/source, repository/ref reachability and Qwen metadata; live offer searches are read-only. Telegram readiness checking is separate from offer discovery so it remains responsive.

48 GB+ VRAM is the full-GPU tier for 2K and faster execution. The 24 GB fallback uses CPU offload and a 48 GB host-RAM floor; more RAM can help enhancement. Start with Standard quality for multiple references. Hardware preference is distinct from download-inclusive cost preference.

## Worker logs and health

```text
/workspace/pixelpilot-bootstrap.log
/workspace/pixelpilot-image-gateway.log
```

The controller probes the authenticated mapped inference port. Health reports model, memory mode, detected VRAM, reference limit and optional enhancer `download_policy`, `cached`, `downloading`, and `fail_open=true`.

Original readiness loads only the base image pipeline. An explicit enhanced request initiates only its required T2I or I2I checkpoint download; that image falls back to Original until the checkpoint is cached. Later requests use enhancement when available. Do not fetch both optional checkpoints just to pass readiness. Stopping or destroying the instance is the provider lifecycle operation; cancelling an asynchronous task is not proof of immediate cessation of a download thread or billing.

## Failure guidance

CUDA out of memory: use Standard quality, fewer/lower-resolution references or a larger GPU. Host RAM pressure: choose more RAM; enhancement temporarily moves/releases diffusion components and may need extra headroom.

Download failure: inspect network, free disk space and logs. `HF_TOKEN` is optional. An enhanced image falling back is expected while its requested checkpoint downloads or when enhancement fails. A `PE_FAIL_OPEN` NameError identifies a stale worker; align its runtime with the published controller ref rather than reintroducing the retired setting.

Uncertain rent after timeout/408/429/5xx: keep the pending label, inspect provider instances and use status/startup reconciliation. Do not clear pending state or rent again until the previous outcome is resolved. Never deliberately create another paid Instance to test ambiguity.

Offer absent before rent: verify whether discovery and validation show the same actual Offer ID. Live evidence showed `/bundles/` could return an empty `id` search for a simultaneously discoverable ask. Use the stored `machine_id`, explicit `verified=true`, `external=false`, `rentable=true`, `no_default=true` and the same allocated storage, then select only the original Offer ID from raw rows. Do not weaken this to accept another offer on the host.

Changed Download/Upload/hourly quote: refresh the list and review the new details; the controller intentionally requires renewed confirmation. A configured Download ceiling is checked again before creation, even for old cached cards.

## Live acceptance and cleanup

First verify prices/readiness through safe reads. A real image-generation/edit test is still pending and requires an authorized session and review of the download-inclusive cost. Before any paid trial, record any pre-existing instances and identify the new trial's unique Instance ID. Test one original generation and one edit as appropriate; optional enhancement may download another checkpoint and should not be enabled merely as a routine smoke test.

Delete only the identified trial Instance, then verify provider absence and local inactive billing/state. Do not touch a pre-existing unrelated Instance. Stop can leave storage charges; deletion is the cleanup step. The old successful trial `52659808` is already documented as deleted and must not be recreated just to repeat that proof.
