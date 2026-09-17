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

## Normal use

1. `/start`
2. Preflight
3. Search Vast
4. Review/rent an offer
5. Wait until Qwen3-Omni is READY
6. Send text/image/voice/audio directly
7. Use `/new` for a new conversation
8. Destroy the Vast instance when finished

## Diagnostics

Run `python scripts/diagnose_vast.py` to inspect instance state, bootstrap log, vLLM process, Hugging Face cache, GPU state and disk usage.

## Memory pressure

If Qwen3-Omni does not fit comfortably on an 80 GB card, lower `MODEL_MAX_LEN` (for example 16384) or choose a GPU with more VRAM.
