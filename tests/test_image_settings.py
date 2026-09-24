import asyncio

from pixelpilot.db import Database
from pixelpilot.services.image_settings import (
    get_state,
    ensure_defaults,
    reset,
    set_aspect_ratio,
    set_quality,
    set_prompt_mode,
    set_steps,
)


def test_image_settings_defaults_and_updates(tmp_path):
    async def scenario():
        db = Database(tmp_path / "db.sqlite3")
        await db.init()
        await ensure_defaults(db)

        state = await get_state(db)
        assert state.aspect_ratio == "1:1"
        assert state.quality == "standard"
        assert state.steps == 40
        assert state.prompt_mode == "original"
        assert state.enhance_prompt is False
        assert state.prompt_mode == "original"
        assert state.enhance_prompt is False
        assert state.size == (1024, 1024)

        await set_aspect_ratio(db, "16:9")
        await set_quality(db, "high")
        await set_steps(db, 30)
        await set_prompt_mode(db, "qwen")
        state = await get_state(db)
        assert state.size == (2752, 1536)
        assert state.steps == 30
        assert state.prompt_mode == "qwen"
        assert state.enhance_prompt is True

        await reset(db)
        state = await get_state(db)
        assert state.size == (1024, 1024)
        assert state.steps == 40

    asyncio.run(scenario())
