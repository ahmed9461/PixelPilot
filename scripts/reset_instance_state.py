from __future__ import annotations

import asyncio

from pixelpilot.config import get_settings
from pixelpilot.db import Database
from pixelpilot.domain import InstancePhase


async def main() -> None:
    settings = get_settings()
    db = Database(settings.database_path)
    await db.init()
    previous_id = await db.get("instance.id")
    previous_phase = await db.get("instance.phase", InstancePhase.NONE.value)
    for key, value in (
        ("instance.id", None),
        ("instance.phase", InstancePhase.NONE.value),
        ("instance.offer", None),
        ("instance.label", None),
        ("instance.pending_label", None),
        ("inference.url", None),
        ("inference.token", None),
        ("inference.active", False),
        ("instance.last_activity_at", None),
        ("cost_guard.warned_instance", None),
        ("cost_guard.warned_activity_at", None),
        ("worker.url", None),
        ("worker.token", None),
        ("generation.active", False),
    ):
        await db.set(key, value)
    await db.event("instance.local_state_reset", {"previous_instance_id": previous_id, "previous_phase": previous_phase})
    print("PixelPilot local instance state reset successfully.")
    print(f"Previous instance: {previous_id or 'none'}")
    print(f"Previous phase: {previous_phase}")
    print("Current phase: NONE")


if __name__ == "__main__":
    asyncio.run(main())
