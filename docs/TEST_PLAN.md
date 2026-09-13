# Test Plan

## Automated local

- Settings validation.
- SQLite KV + generation persistence.
- Owner check.
- Vast offer query + normalization + mapped port parsing.
- Instance ID extraction.
- Official Krea model manifest.
- Workflow API patching + history image parsing.
- Fake full orchestration lifecycle:
  Search -> Rent -> Ready -> Generate -> Download -> Stop -> Start -> Destroy.
- Worker FastAPI:
  auth -> health -> submit -> job -> image.
- Preflight.

Current result: **31 passed**.

## Compile

```bash
python -m compileall -q src scripts
```

## Live acceptance required once credentials exist

1. Search real offers.
2. Rent one 48GB offer.
3. Verify port mapping and Caddy auth.
4. Verify all four model files download.
5. Verify Comfy `/system_stats` and model lists.
6. Generate one 1024×1024 image.
7. Telegram Preview + Original.
8. Same-seed reproducibility check.
9. Destroy.
10. Confirm no active instance remains.
