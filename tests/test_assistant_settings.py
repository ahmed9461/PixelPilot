import asyncio

from pixelpilot.db import Database
from pixelpilot.services.assistant_settings import (
    LEGACY_V2_PERSONAS,
    LEGACY_V4_PERSONAS,
    apply_group_selection,
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
        assert state["creativity_pct"] == 30
        assert state["diversity_pct"] == 80
        assert state["response_length_pct"] == 100
        assert state["repetition_guard_pct"] == 0
        assert await effective_system_prompt(db) == ""
        params = await generation_params(db, max_output_tokens=2048)
        assert params == {"temperature": 0.3, "top_p": 0.8, "max_tokens": 2048, "repetition_penalty": 1.0, "top_k": 20}
    asyncio.run(scenario())


def test_selected_profiles_are_structured_and_can_be_replaced(tmp_path):
    async def scenario():
        db = Database(tmp_path / "settings.sqlite3")
        await db.init()
        await set_state(db, "persona", "analyst")
        await set_state(db, "tone", "gentle")
        original = await effective_system_prompt(db)
        assert "[شخصية: محلل حاد وهادئ]" in original
        assert "[نبرة: لطيفة وهادئة]" in original
        assert len(await get_prompt(db, "persona", "analyst")) > 450

        await set_prompt(db, "persona", "analyst", "CUSTOM ANALYST PROMPT")
        replaced = await effective_system_prompt(db)
        assert "CUSTOM ANALYST PROMPT" in replaced
        assert "[دور الشخصية: محلل دقيق عالي الاعتمادية]" not in replaced

        await reset_prompt(db, "persona", "analyst")
        restored = await get_prompt(db, "persona", "analyst")
        assert "[شخصية: محلل حاد وهادئ]" in restored
    asyncio.run(scenario())


def test_generation_percentages_and_context_are_runtime_settings(tmp_path):
    async def scenario():
        db = Database(tmp_path / "settings.sqlite3")
        await db.init()
        await set_state(db, "creativity_pct", 50)
        await set_state(db, "diversity_pct", 80)
        await set_state(db, "response_length_pct", 100)
        await set_state(db, "repetition_guard_pct", 80)
        params = await generation_params(db, max_output_tokens=2048)
        assert params == {"temperature": 0.5, "top_p": 0.8, "max_tokens": 2048, "repetition_penalty": 1.16, "top_k": 20}

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
        assert "[شخصية: محلل حاد وهادئ]" in analyst
        assert direct == "MY CUSTOM DIRECT PROMPT"

    asyncio.run(scenario())



def test_dramatic_persona_has_visible_everyday_signature_and_anti_loop_rules(tmp_path):
    async def scenario():
        db = Database(tmp_path / "settings.sqlite3")
        await db.init()
        prompt = await get_prompt(db, "persona", "dramatic")
        assert "الكلام اليومي" in prompt
        assert "لا تكرر الحدث نفسه" in prompt
        assert "لا تستخدم عبارة مميزة واحدة في كل رد" in prompt
    asyncio.run(scenario())



def test_v2_persona_defaults_upgrade_to_v3_but_marked_owner_edits_survive(tmp_path):
    async def scenario():
        db = Database(tmp_path / "settings.sqlite3")
        await db.init()

        await db.set("assistant.prompts.version", 2)
        await db.set("assistant.prompt.persona.dramatic", LEGACY_V2_PERSONAS["dramatic"])
        await db.set("assistant.prompt.persona.friend", LEGACY_V2_PERSONAS["friend"])
        await db.set("assistant.prompt.edited.persona.friend", True)

        await ensure_defaults(db)

        dramatic = await get_prompt(db, "persona", "dramatic")
        friend = await get_prompt(db, "persona", "friend")
        assert dramatic != LEGACY_V2_PERSONAS["dramatic"]
        assert "[شخصية: سينمائية عاطفية]" in dramatic
        assert friend == LEGACY_V2_PERSONAS["friend"]
        assert await db.get("assistant.prompts.version") == 5

    asyncio.run(scenario())


def test_manual_prompt_edit_marker_is_written_and_reset(tmp_path):
    async def scenario():
        db = Database(tmp_path / "settings.sqlite3")
        await db.init()
        await set_prompt(db, "persona", "dramatic", "CUSTOM")
        assert await db.get("assistant.prompt.edited.persona.dramatic") is True
        await reset_prompt(db, "persona", "dramatic")
        assert await db.get("assistant.prompt.edited.persona.dramatic") is False

    asyncio.run(scenario())



def test_v2_generation_defaults_migrate_to_daily_assistant_profile(tmp_path):
    async def scenario():
        db = Database(tmp_path / "settings.sqlite3")
        await db.init()
        await db.set_many({
            "assistant.state.creativity_pct": 70,
            "assistant.state.diversity_pct": 80,
            "assistant.state.response_length_pct": 100,
            "assistant.state.repetition_guard_pct": 0,
            "assistant.generation.version": 2,
        })
        await ensure_defaults(db)
        state = await get_state(db)
        assert state["creativity_pct"] == 30
        assert state["diversity_pct"] == 80
        assert state["response_length_pct"] == 100
        assert state["repetition_guard_pct"] == 0
        assert await db.get("assistant.generation.version") == 3

    asyncio.run(scenario())


def test_owner_edited_generation_value_survives_profile_migration(tmp_path):
    async def scenario():
        db = Database(tmp_path / "settings.sqlite3")
        await db.init()
        await db.set_many({
            "assistant.state.creativity_pct": 90,
            "assistant.state.diversity_pct": 80,
            "assistant.state.response_length_pct": 100,
            "assistant.state.repetition_guard_pct": 0,
            "assistant.generation.version": 2,
            "assistant.generation.edited.creativity_pct": True,
        })
        await ensure_defaults(db)
        state = await get_state(db)
        assert state["creativity_pct"] == 90
        assert state["diversity_pct"] == 80
        assert state["repetition_guard_pct"] == 0
        assert await db.get("assistant.generation.version") == 3

    asyncio.run(scenario())



def test_selecting_persona_isolates_secondary_style_layers(tmp_path):
    async def scenario():
        db = Database(tmp_path / "settings.sqlite3")
        await db.init()
        await set_state(db, "tone", "sarcastic")
        await set_state(db, "reasoning", "deep")
        await set_state(db, "format", "structured")
        await set_state(db, "language", "ar")
        await db.set_many({
            "assistant.state.custom_prompt": "تكلم كفيلسوف خيالي دائمًا",
            "assistant.state.custom_prompt_enabled": True,
        })

        await apply_group_selection(db, "persona", "friend")
        state = await get_state(db)
        assert state["persona"] == "friend"
        assert state["tone"] == "balanced"
        assert state["reasoning"] == "auto"
        assert state["format"] == "auto"
        assert state["language"] == "ar"
        assert state["custom_prompt"] == "تكلم كفيلسوف خيالي دائمًا"
        assert state["custom_prompt_enabled"] is False

        prompt = await effective_system_prompt(db)
        assert "[شخصية: صديق يومي ذكي]" in prompt
        assert "تكلم كفيلسوف خيالي دائمًا" not in prompt
        assert "فلسفة أو استعارات أو خيال" in prompt

    asyncio.run(scenario())


def test_custom_prompt_is_injected_only_when_explicitly_enabled(tmp_path):
    async def scenario():
        db = Database(tmp_path / "settings.sqlite3")
        await db.init()
        await db.set_many({
            "assistant.state.custom_prompt": "CUSTOM EXTRA LAYER",
            "assistant.state.custom_prompt_enabled": False,
        })
        assert "CUSTOM EXTRA LAYER" not in await effective_system_prompt(db)

        await set_state(db, "custom_prompt_enabled", True)
        assert "CUSTOM EXTRA LAYER" in await effective_system_prompt(db)

    asyncio.run(scenario())


def test_existing_custom_prompt_activation_is_preserved_on_first_upgrade(tmp_path):
    async def scenario():
        db = Database(tmp_path / "settings.sqlite3")
        await db.init()
        await db.set("assistant.state.custom_prompt", "OLD CUSTOM")
        await ensure_defaults(db)
        state = await get_state(db)
        assert state["custom_prompt"] == "OLD CUSTOM"
        assert state["custom_prompt_enabled"] is True

    asyncio.run(scenario())


def test_v4_persona_default_upgrades_to_v5_but_owner_edit_survives(tmp_path):
    async def scenario():
        db = Database(tmp_path / "settings.sqlite3")
        await db.init()
        await db.set_many({
            "assistant.prompts.version": 4,
            "assistant.prompt.persona.friend": LEGACY_V4_PERSONAS["friend"],
            "assistant.prompt.persona.analyst": "MY CUSTOM ANALYST",
            "assistant.prompt.edited.persona.analyst": True,
        })

        await ensure_defaults(db)

        friend = await get_prompt(db, "persona", "friend")
        analyst = await get_prompt(db, "persona", "analyst")
        assert friend != LEGACY_V4_PERSONAS["friend"]
        assert "لا تحوّل الكلام اليومي إلى فلسفة" in friend
        assert analyst == "MY CUSTOM ANALYST"
        assert await db.get("assistant.prompts.version") == 5

    asyncio.run(scenario())
