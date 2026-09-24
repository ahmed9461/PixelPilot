import inspect

from pixelpilot.bot.routers import chat, home, servers, settings


FORBIDDEN_UI_TERMS = (
    "vllm",
    "whisper",
    "system prompt",
    "developer prompt",
    "persona",
)


def _assert_clean(text: str) -> None:
    lowered = text.lower()
    for term in FORBIDDEN_UI_TERMS:
        assert term not in lowered, f"obsolete UI term leaked into Telegram copy: {term}"


def test_welcome_copy_is_image_focused():
    _assert_clean(home.WELCOME)
    assert "صورة" in home.WELCOME


def test_help_copy_is_image_focused():
    source = inspect.getsource(chat.chat_help)
    _assert_clean(source)
    assert "تعديل" in source


def test_image_settings_have_no_persona_controls():
    source = inspect.getsource(settings)
    _assert_clean(source)
    assert "إعدادات الصور" in source


def test_server_screens_have_no_retired_runtime_terms():
    for handler in (
        servers.preflight,
        servers.search,
        servers.offer_details,
        servers.rent,
        servers.destroy_confirm,
        servers.start_instance,
        servers.status,
    ):
        _assert_clean(inspect.getsource(handler))
