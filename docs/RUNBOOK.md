# Runbook

## Controller setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python scripts/configure_secrets.py
python scripts/preflight.py
python -m pixelpilot.main
```

## Existing installation migration to v0.6

For an installation such as `/opt/pixelpilot`:

```bash
cd /opt/pixelpilot
systemctl stop pixelpilot.service
git pull --ff-only origin main
/opt/pixelpilot/.venv/bin/python -m pip install -e .
/opt/pixelpilot/.venv/bin/python scripts/migrate_economy_profile.py
/opt/pixelpilot/.venv/bin/python scripts/preflight.py
systemctl start pixelpilot.service
systemctl status pixelpilot.service --no-pager -l
```

The migration helper creates a backup of `.env` and changes only non-secret runtime/profile values. Telegram, Vast and Hugging Face credentials are preserved.

The v0.6 profile uses:
- Qwen3-VL-30B-A3B-Instruct-FP8
- Whisper turbo
- 48GB+ VRAM search
- 100GB disk
- 16K context
- $0.50/hour hard ceiling

## Existing Vast instance after Controller upgrade

A currently running Vast instance may still be serving the old runtime. Updating the Controller alone cannot replace model processes already running remotely.

Use one of these:
1. **Preferred while testing:** delete the old instance and rent a fresh offer. The new instance clones current `main` and provisions Qwen3-VL + Whisper cleanly.
2. Stop then Start the existing instance if its onstart hook is intact; it fetches current `main` before bootstrap. Confirm diagnostics show the new model before testing.

Do not assume READY from an old instance means the new runtime is active.

## Normal use

1. `/start`
2. Run readiness check.
3. Search Vast.
4. Review/rent an offer.
5. Wait for READY; READY now requires both Qwen3-VL and Whisper gateway health.
6. Send text/image/video/Voice/audio directly.
7. Use `/new` for a clean conversation.
8. Check server status/cost as needed.
9. Delete the Vast instance when finished.

## Diagnostics

```bash
cd /opt/pixelpilot
/opt/pixelpilot/.venv/bin/python scripts/diagnose_vast.py
```

The model line should be:
```text
Qwen/Qwen3-VL-30B-A3B-Instruct-FP8
```

Gateway `health: OK` means both the public gateway and its required runtime are ready.

For remote bootstrap failures, inspect Vast instance logs. The bootstrap also writes:
- `/workspace/pixelpilot-bootstrap.log`
- `/workspace/pixelpilot-vllm.log`
- `/workspace/pixelpilot-gateway.log`

## Memory pressure

Default vLLM GPU utilization is 0.82 to reserve headroom for Whisper. Whisper auto mode uses GPU only if enough free VRAM remains; otherwise it loads on CPU.

On a tight 48GB host:
1. Keep `WHISPER_DEVICE=auto`.
2. Do not raise `MODEL_GPU_MEMORY_UTILIZATION` first.
3. Check actual VRAM use and speech latency.
4. If Qwen3-VL itself is tight, lower `MODEL_MAX_LEN` before changing to a more expensive GPU.
