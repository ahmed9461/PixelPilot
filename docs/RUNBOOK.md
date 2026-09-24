# Runbook

## Controller update

On the persistent controller host:

```bash
cd /opt/pixelpilot
git fetch origin main
git reset --hard origin/main
source .venv/bin/activate
pip install -e .
python scripts/preflight.py
sudo systemctl restart pixelpilot.service
sudo systemctl status pixelpilot.service --no-pager
```

Do not merge/deploy the new GPU runtime while deliberately keeping the old controller code active; the protocols differ.

## Preflight

```bash
python scripts/preflight.py
```

Expected:
- Telegram credentials valid locally
- Vast API configured
- repository/template source configured
- Qwen-Image-2.1 metadata reachable
- at least one matching GPU offer if the marketplace currently has one

## GPU profiles

Recommended:
- 48 GB+ VRAM for 2K and faster execution

Fallback:
- 24 GB VRAM with automatic model CPU offload
- use Standard quality first when editing multiple references

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
