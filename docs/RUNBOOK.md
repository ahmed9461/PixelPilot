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

## Existing server migration to the economy profile

For an existing installation such as `/opt/pixelpilot`:

```bash
cd /opt/pixelpilot
git pull --ff-only origin main
/opt/pixelpilot/.venv/bin/python -m pip install -e .
/opt/pixelpilot/.venv/bin/python scripts/migrate_economy_profile.py
/opt/pixelpilot/.venv/bin/python scripts/preflight.py
```

The migration helper backs up `.env` first and changes only non-secret model/Vast profile values. Telegram/Vast/Hugging Face credentials are left unchanged.

## Normal use

1. `/start`
2. Preflight
3. Search Vast
4. Review/rent an offer
5. Wait until Qwen2.5-Omni-7B is READY
6. Send text/image/voice/audio directly
7. Use `/new` for a new conversation
8. Destroy the Vast instance when finished

## Diagnostics

Run `python scripts/diagnose_vast.py` to inspect instance state, bootstrap log, vLLM process, Hugging Face cache, GPU state and disk usage.

## Memory pressure

The default profile uses 48GB+ VRAM and `MODEL_MAX_LEN=8192`. If a specific 48GB card is still tight, reduce `MODEL_MAX_LEN` before considering a higher-cost GPU. Do not silently change the model to 3B; that should remain an explicit quality/cost choice.
