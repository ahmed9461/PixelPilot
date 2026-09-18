from pixelpilot.bot.routers.chat import _draft_preview, _trim_history


def test_history_trim_never_starts_with_assistant():
    messages = [
        {"role": "user", "content": "1"},
        {"role": "assistant", "content": "2"},
        {"role": "user", "content": "3"},
        {"role": "assistant", "content": "4"},
    ]
    assert _trim_history(messages, 3) == [
        {"role": "user", "content": "3"},
        {"role": "assistant", "content": "4"},
    ]



def test_draft_preview_keeps_latest_text_inside_telegram_limit():
    assert _draft_preview("abc", 4) == "abc"
    assert _draft_preview("abcdefgh", 5) == "…efgh"
