from __future__ import annotations

import asyncio
import json

from vastai import VastAI

from pixelpilot.config import get_settings
from pixelpilot.db import Database

COMMANDS = [
    ("WORKSPACE", "ls -lah"),
    ("PIXELPILOT ROOT", "ls -lah PixelPilot"),
    ("BOOTSTRAP LOG", "tail -n 250 pixelpilot-bootstrap.log 2>/dev/null || true"),
    ("VLLM PROCESSES", "ps aux | grep -E '[v]llm|[a]pi_server' || true"),
    ("HF CACHE", "du -sh hf-cache 2>/dev/null || true"),
    ("GPU", "nvidia-smi || true"),
    ("WORKSPACE DISK USAGE", "du -d 2 -h . | sort -h | tail -n 80"),
]


async def _call(client: VastAI, method: str, **kwargs):
    fn = getattr(client, method)
    return await asyncio.to_thread(fn, **kwargs)


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
    print(f"PixelPilot live diagnostics — instance {instance_id}\n")
    print("===== INSTANCE =====")
    try:
        info = await _call(client, "show_instance", id=int(instance_id))
        if isinstance(info, str):
            try:
                info = json.loads(info)
            except json.JSONDecodeError:
                pass
        if isinstance(info, dict) and isinstance(info.get("instances"), dict):
            info = info["instances"]
        if isinstance(info, dict):
            summary = {key: info.get(key) for key in ("id", "actual_status", "intended_status", "cur_state", "status_msg", "public_ipaddr", "ssh_host", "ssh_port", "ports", "onstart") if info.get(key) is not None}
            print(json.dumps(summary, ensure_ascii=False, indent=2))
        else:
            print(info)
    except Exception as exc:
        print(f"ERROR: {exc}")
    print("\n===== VAST INSTANCE LOGS =====")
    try:
        logs = await _call(client, "logs", instance_id=int(instance_id), tail=250)
        print(logs.rstrip() if isinstance(logs, str) else logs)
    except Exception as exc:
        print(f"ERROR: {exc}")
    for title, command in COMMANDS:
        print(f"\n===== {title} =====")
        try:
            output = await _call(client, "execute", id=int(instance_id), command=command)
        except Exception as exc:
            print(f"ERROR: {exc}")
            continue
        print(output.rstrip() if isinstance(output, str) else output)


if __name__ == "__main__":
    asyncio.run(main())
