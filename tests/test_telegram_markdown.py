"""Regression tests for Telegram Markdown rendering of AI replies."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

from pixelpilot.bot.telegram_markdown import MAX_TELEGRAM_UTF16, format_model_reply


def _render(source: str):
    parts = format_model_reply(source)
    return "".join(part.text for part in parts), parts


def _entities(chunk, kind: str):
    return [entity for entity in chunk.entities if entity.type == kind]


def test_markdown_heading_bold_italic_inline_code_and_bullets():
    text, parts = _render(
        "### 1. تثبيت المكتبات **Dependencies**\n\n"
        "* `Requirement already satisfied` يعني **موجود**\n"
        "* النص *مائل*\n"
    )
    assert text.startswith("1. تثبيت المكتبات Dependencies\n\n• Requirement already satisfied")
    assert "`" not in text
    assert "###" not in text
    assert "**" not in text
    assert len(parts) == 1
    entities = parts[0].entities
    assert any(e.type == "bold" for e in entities)
    assert any(e.type == "italic" for e in entities)
    assert any(e.type == "code" for e in entities)


def test_code_fence_preserves_literal_markdown_inside_pre():
    text, parts = _render("مثال:\n\n```bash\necho '# محفوظ **كما هو**'\n```")
    assert "```" not in text
    assert "echo '# محفوظ **كما هو**'" in text
    assert len(_entities(parts[0], "pre")) == 1
    assert not _entities(parts[0], "code")


def test_emoji_and_arabic_use_utf16_entity_offsets():
    text, parts = _render("🤖 **أهلًا** 🧠")
    assert text == "🤖 أهلًا 🧠"
    bold = _entities(parts[0], "bold")
    assert len(bold) == 1
    # Emoji takes two UTF-16 code units, space one.
    assert bold[0].offset == 3
    assert bold[0].length == len("أهلًا".encode("utf-16-le")) // 2


def test_link_url_safety_and_untrusted_raw_html():
    text, parts = _render(
        "[مصدر](https://example.org/read?q=1&x=2) "
        "[تنبيه](javascript:alert(1)) <script>alert(1)</script>"
    )
    assert "مصدر" in text and "تنبيه" in text
    assert "<script>" in text  # harmless plain text; not interpreted as HTML
    links = _entities(parts[0], "text_link")
    assert len(links) == 1
    assert links[0].url == "https://example.org/read?q=1&x=2"


def test_long_replies_split_with_valid_entity_intersections():
    source = "**" + ("🔥نص " * 2000) + "**"
    text, parts = _render(source)
    assert text == "🔥نص " * 2000
    assert len(parts) > 1
    assert all(0 < len(p.text.encode("utf-16-le")) // 2 <= MAX_TELEGRAM_UTF16 for p in parts)
    for part in parts:
        length = len(part.text.encode("utf-16-le")) // 2
        for entity in part.entities:
            assert entity.offset >= 0
            assert entity.length > 0
            assert entity.offset + entity.length <= length
        assert len(_entities(part, "bold")) == 1


def test_fenced_code_longer_than_telegram_limit_is_split_safely():
    content = "print('مرحبًا')\n" * 320
    text, parts = _render("```python\n" + content + "```")
    assert text == content.rstrip("\n")
    assert len(parts) > 1
    assert all(_entities(part, "pre") for part in parts)


def test_table_and_numbered_list_remain_readable():
    text, parts = _render(
        "| الحالة | النتيجة |\n|---|---|\n| خدمة | نشطة |\n\n"
        "1. أولًا\n2. ثانيًا\n"
    )
    assert "الحالة  |  النتيجة" in text
    assert "خدمة  |  نشطة" in text
    assert "1. أولًا" in text and "2. ثانيًا" in text
    assert len(_entities(parts[0], "bold")) == 2


def test_chat_router_sends_markdown_as_entities_without_parse_mode(monkeypatch):
    from pixelpilot.bot.routers import chat

    class FakeDB:
        async def get(self, key, default=None):
            return "ready"

    class FakeOrchestrator:
        settings = SimpleNamespace(chat_max_images=3, chat_model_id="Qwen/Qwen3.5-9B")
        db = FakeDB()

        async def chat(self, prompt, reference_images=()):
            return "## العنوان\n\n- **نتيجة مهمة** 🫡\n- `معلومة`"

    class FakeMessage:
        def __init__(self):
            self.sent = []

        async def answer(self, text, **kwargs):
            self.sent.append((text, kwargs))
            return SimpleNamespace(delete=self._delete)

        async def _delete(self):
            return None

    monkeypatch.setattr(chat, "orch", lambda: FakeOrchestrator())
    msg = FakeMessage()
    asyncio.run(chat._reply(msg, "اشرح لي النتيجة"))

    assert len(msg.sent) == 2
    first, kwargs = msg.sent[-1]
    assert "#" not in first and "**" not in first and "`" not in first
    assert "العنوان" in first and "• نتيجة مهمة 🫡" in first
    assert kwargs["parse_mode"] is None
    assert any(entity.type == "bold" for entity in kwargs["entities"])


def test_plain_text_is_passed_through():
    raw = "نص عادي يحتوي على علامة * وحدها، ورمز # في منتصف الجملة."
    actual, parts = _render(raw)
    assert actual == raw
    assert len(parts) == 1
