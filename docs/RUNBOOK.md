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
- GPU offers satisfy the configured price, VRAM, host-RAM, reliability, disk and network filters

## GPU profiles

Recommended:
- 48 GB+ VRAM for 2K and faster full-GPU execution

Fallback:
- 24 GB VRAM with automatic model CPU offload
- at least 48 GB host RAM
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

Host RAM pressure while using a 24 GB GPU:
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

## Lifecycle

Stop pauses GPU billing according to provider behavior but storage can still incur cost. Destroy removes the instance and records the final PixelPilot billing estimate.
