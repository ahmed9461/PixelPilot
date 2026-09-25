# Runbook

## Controller update

Run the update from the directory that already contains the persistent PixelPilot controller clone. Do not assume a fixed path or service name.

```bash
cd /path/to/your/PixelPilot
git fetch origin main
git reset --hard origin/main
```

Then use the Python environment that the controller already runs with. If the project has a local virtual environment:

```bash
source .venv/bin/activate
pip install -e .
python scripts/preflight.py
```

If the controller is managed by systemd, first identify the actual unit name instead of assuming one:

```bash
systemctl list-units --type=service --all | grep -i pixelpilot
```

Then restart the unit that is actually present:

```bash
sudo systemctl restart <actual-unit-name>
sudo systemctl status <actual-unit-name> --no-pager
```

If the controller is run by Docker, tmux, screen, supervisord, or another process manager, restart it through that same manager.

The controller and GPU worker API changed together in the Qwen-Image-2.1 migration. Update the persistent controller before renting a fresh GPU worker.

## Preflight

```bash
python scripts/preflight.py
```

Expected:
- Telegram credentials valid locally
- Vast API configured
- repository/template source configured
- Qwen-Image-2.1 metadata reachable
- GPU offers satisfy the configured price, VRAM, reliability, disk and network filters; host RAM is filtered on CPU-offload offers

## GPU profiles

Recommended:
- 48 GB+ VRAM for 2K and faster full-GPU execution

Fallback:
- 24 GB VRAM with automatic model CPU offload
- at least 48 GB host RAM for CPU offload; more may help optional enhancement
- start with Standard quality when editing multiple references

## Vast worker logs

The bootstrap log is:

```text
/workspace/pixelpilot-bootstrap.log
```

The image gateway log is:

```text
/workspace/pixelpilot-image-gateway.log
```

## Health

The controller probes the authenticated public mapped port. A ready worker reports:
- configured model id
- memory mode
- detected GPU VRAM
- maximum reference count

## Failure guidance

CUDA out of memory:
- switch to Standard quality
- reduce reference-image count
- use a 48 GB+ GPU

Host RAM pressure while using a 24 GB GPU or the on-demand prompt enhancer:
- choose a host with more system RAM
- prefer a 48 GB+ GPU to avoid CPU model offload

Model download failure:
- check worker network
- optionally configure `HF_TOKEN`
- inspect the bootstrap log

Worker is running but not ready:
- inspect the image gateway log
- verify the model finished downloading/loading
- verify the mapped inference port exists

Qwen Enhance initially uses the original prompt:
- optional T2I/I2I weights are downloading in the background; check the image gateway log and disk space
- the result reports fallback; retry after the requested checkpoint is cached

Rent outcome is uncertain after a timeout, 408/429 or 5xx:
- inspect the controller's pending label and Vast instances; the controller blocks another rent
- use the Telegram status control to retry exact-label reconciliation, or restart the controller to recover
- do not reset pending state or rent again until the previous request is confirmed absent or its Instance ID is recovered

An offer disappears before rent:
- This is before `create_instance`; it does not create a paid instance. Refresh and compare the actual Offer IDs shown on the cards, since identical GPU/price labels may be different asks.
- If the same ID appears again and still fails, run a read-only exact-ID Vast search with the configured API key to distinguish a marketplace change from a lookup mismatch. Do not bypass exact-ID validation or rent a different ask automatically.

## Lifecycle

Stop pauses GPU billing according to provider behavior but storage can still incur cost. Destroy removes the instance and records the final PixelPilot billing estimate.
