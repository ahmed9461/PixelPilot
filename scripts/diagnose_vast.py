from __future__ import annotations

import asyncio

from vastai import VastAI

from pixelpilot.config import get_settings
from pixelpilot.db import Database


COMMANDS = [
    ("BOOTSTRAP LOG", "tail -n 180 /workspace/pixelpilot-bootstrap.log"),
    ("WORKSPACE", "ls -lah /workspace"),
    ("PROCESSES", "ps aux"),
    ("COMFYUI LOG", "tail -n 120 /workspace/comfyui.log"),
]


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

    for title, command in COMMANDS:
        print(f"\n===== {title} =====")
        try:
            output = await asyncio.to_thread(client.execute, id=int(instance_id), command=command)
        except Exception as exc:
            print(f"ERROR: {exc}")
            continue
        if isinstance(output, str):
            print(output.rstrip())
        else:
            print(output)


if __name__ == "__main__":
    asyncio.run(main())
