import inspect

from pixelpilot.bot.routers import chat, home, servers


FORBIDDEN_UI_TERMS = (
    "qwen",
    "vllm",
    "vast.ai",
    "system prompt",
    "developer prompt",
    "model:",
    "inference:",
)


def _assert_clean(text: str) -> None:
    lowered = text.lower()
    for term in FORBIDDEN_UI_TERMS:
        assert term not in lowered, f"technical UI term leaked into Telegram copy: {term}"


def test_welcome_copy_stays_user_facing():
    _assert_clean(home.WELCOME)


def test_help_copy_stays_user_facing():
    _assert_clean(inspect.getsource(chat.chat_help))


def test_server_screens_stay_user_facing():
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
