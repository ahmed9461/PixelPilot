import asyncio

from pixelpilot.db import Database
from pixelpilot.services.assistant_settings import (
    context_policy,
    effective_system_prompt,
    generation_params,
    get_prompt,
    get_state,
    reset_prompt,
    set_prompt,
    set_state,
)


def test_default_profile_has_no_hidden_prompt_and_stable_sampling(tmp_path):
    async def scenario():
        db = Database(tmp_path / "settings.sqlite3")
        await db.init()
        state = await get_state(db)
        assert state["persona"] == "neutral"
        assert state["tone"] == "balanced"
        assert state["diversity_pct"] == 100
        assert state["response_length_pct"] == 100
        assert await effective_system_prompt(db) == ""
        params = await generation_params(db, max_output_tokens=2048)
        assert params == {"temperature": 0.0, "top_p": 1.0, "max_tokens": 2048}
    asyncio.run(scenario())


def test_selected_profiles_compose_and_can_be_replaced_from_db(tmp_path):
    async def scenario():
        db = Database(tmp_path / "settings.sqlite3")
        await db.init()
        await set_state(db, "persona", "analyst")
        await set_state(db, "tone", "gentle")
        original = await effective_system_prompt(db)
        assert "حلّل" in original
        assert "لطيفة" in original

        await set_prompt(db, "persona", "analyst", "CUSTOM ANALYST PROMPT")
        replaced = await effective_system_prompt(db)
        assert "CUSTOM ANALYST PROMPT" in replaced
        assert "حلّل المسألة" not in replaced

        await reset_prompt(db, "persona", "analyst")
        restored = await get_prompt(db, "persona", "analyst")
        assert "حلّل" in restored
    asyncio.run(scenario())


def test_generation_percentages_and_context_are_runtime_settings(tmp_path):
    async def scenario():
        db = Database(tmp_path / "settings.sqlite3")
        await db.init()
        await set_state(db, "creativity_pct", 50)
        await set_state(db, "diversity_pct", 80)
        await set_state(db, "response_length_pct", 100)
        params = await generation_params(db, max_output_tokens=2048)
        assert params == {"temperature": 0.4, "top_p": 0.8, "max_tokens": 2048}

        await set_state(db, "context_enabled", False)
        await set_state(db, "context_messages", 20)
        assert await context_policy(db, default_messages=10) == (False, 20)
    asyncio.run(scenario())
