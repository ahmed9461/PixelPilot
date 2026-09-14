from __future__ import annotations

import asyncio
import json
from typing import Any

from vastai import VastAI

from pixelpilot.config import get_settings
from pixelpilot.db import Database


# Vast's execute endpoint is intentionally constrained. According to Vast's
# current CLI/API docs it accepts ls/rm/du, not arbitrary shell commands such
# as tail, cat, ps, grep, etc. Keep diagnostics inside that supported subset.
COMMANDS = [
    ("WORKSPACE", "ls -lah /workspace"),
    ("BOOTSTRAP LOG FILE", "ls -lah /workspace/pixelpilot-bootstrap.log"),
    ("COMFYUI LOG FILE", "ls -lah /workspace/comfyui.log"),
    ("COMFYUI ROOT", "ls -lah /workspace/ComfyUI"),
    ("KREA DIFFUSION MODELS", "ls -lah /workspace/ComfyUI/models/diffusion_models"),
    ("TEXT ENCODERS", "ls -lah /workspace/ComfyUI/models/text_encoders"),
    ("VAE", "ls -lah /workspace/ComfyUI/models/vae"),
    ("WORKSPACE DISK USAGE", "du -d2 -h /workspace"),
]


def _pick(raw: Any, *names: str) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    return {name: raw.get(name) for name in names if raw.get(name) is not None}


async def main() -> None:
    settings = get_settings()
    if not settings.vast_api_key:
        raise SystemExit("VAST_API_KEY is not configured")

    db = Database(settings.database_path)
    await db.init()
    instance_id = await db.get("instance.id")
    if not instance_id:
        raise SystemExit("PixelPilot has no current instance id in its database")

    client = VastAI(api_key=settings.vast_api_key, raw=True, quiet=True)
    instance_id = int(instance_id)
    print(f"PixelPilot live diagnostics — instance {instance_id}\n")

    print("===== INSTANCE =====")
    try:
        raw = await asyncio.to_thread(client.show_instance, id=instance_id)
        print(json.dumps(_pick(
            raw,
            "id",
            "actual_status",
            "intended_status",
            "cur_state",
            "status_msg",
            "public_ipaddr",
            "ssh_host",
            "ssh_port",
            "ports",
            "onstart",
        ), ensure_ascii=False, indent=2, default=str))
    except Exception as exc:
        print(f"ERROR: {exc}")

    print("\n===== VAST INSTANCE LOGS =====")
    try:
        output = await asyncio.to_thread(client.logs, instance_id=instance_id, tail="250")
        if isinstance(output, str):
            print(output.rstrip())
        else:
            print(output)
    except Exception as exc:
        print(f"ERROR: {exc}")

    for title, command in COMMANDS:
        print(f"\n===== {title} =====")
        try:
            output = await asyncio.to_thread(client.execute, id=instance_id, command=command)
        except Exception as exc:
            print(f"ERROR: {exc}")
            continue
        if isinstance(output, str):
            print(output.rstrip())
        else:
            print(output)


if __name__ == "__main__":
    asyncio.run(main())
