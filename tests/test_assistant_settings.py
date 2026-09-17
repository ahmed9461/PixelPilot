import asyncio

from pixelpilot.db import Database
from pixelpilot.services.assistant_settings import (
    context_policy,
    effective_system_prompt,
    ensure_defaults,
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


def test_selected_profiles_are_structured_and_can_be_replaced(tmp_path):
    async def scenario():
        db = Database(tmp_path / "settings.sqlite3")
        await db.init()
        await set_state(db, "persona", "analyst")
        await set_state(db, "tone", "gentle")
        original = await effective_system_prompt(db)
        assert "[دور الشخصية: محلل دقيق عالي الاعتمادية]" in original
        assert "[نبرة: لطيفة وهادئة]" in original
        assert len(await get_prompt(db, "persona", "analyst")) > 450

        await set_prompt(db, "persona", "analyst", "CUSTOM ANALYST PROMPT")
        replaced = await effective_system_prompt(db)
        assert "CUSTOM ANALYST PROMPT" in replaced
        assert "[دور الشخصية: محلل دقيق عالي الاعتمادية]" not in replaced

        await reset_prompt(db, "persona", "analyst")
        restored = await get_prompt(db, "persona", "analyst")
        assert "[دور الشخصية: محلل دقيق عالي الاعتمادية]" in restored
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


def test_legacy_default_prompts_upgrade_but_custom_edits_survive(tmp_path):
    async def scenario():
        db = Database(tmp_path / "settings.sqlite3")
        await db.init()
        old_analyst = "حلّل المسألة بدقة، فرّق بين الحقائق والافتراضات، وانتبه للتفاصيل والتناقضات. قدّم نتيجة عملية ومفهومة بدل الاستعراض."
        await db.set("assistant.prompt.persona.analyst", old_analyst)
        await db.set("assistant.prompt.tone.direct", "MY CUSTOM DIRECT PROMPT")
        await db.set("assistant.prompts.version", 1)

        await ensure_defaults(db)

        analyst = await get_prompt(db, "persona", "analyst")
        direct = await get_prompt(db, "tone", "direct")
        assert analyst != old_analyst
        assert "[دور الشخصية: محلل دقيق عالي الاعتمادية]" in analyst
        assert direct == "MY CUSTOM DIRECT PROMPT"

    asyncio.run(scenario())
