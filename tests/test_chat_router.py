"""Telegram routing regressions; no Telegram network calls."""
import asyncio
from types import SimpleNamespace

from pixelpilot.bot.routers import chat
from pixelpilot.domain import ReferenceImage


def message(**kwargs):
    data = dict(chat=SimpleNamespace(id=42), message_thread_id=None,
                text="  original  ", reply_to_message=None, media_group_id=None)
    data.update(kwargs)
    return SimpleNamespace(**data)


def test_generate_mode_keeps_original_prompt_whitespace(monkeypatch):
    async def scenario():
        captured = []
        async def mode(_):
            return "generate"
        async def create(_, prompt, *args):
            captured.append(prompt)
        monkeypatch.setattr(chat, "_mode", mode)
        monkeypatch.setattr(chat, "_create_image", create)
        await chat.receive_text(message())
        assert captured == ["  original  "]
    asyncio.run(scenario())


def test_edit_mode_does_not_accidentally_send_text_to_chat_model(monkeypatch):
    async def scenario():
        replies = []
        async def mode(_):
            return "edit"
        async def answer(text):
            replies.append(text)
        async def forbidden(*args, **kwargs):
            raise AssertionError("missing-image edit was routed to chat")
        monkeypatch.setattr(chat, "_mode", mode)
        monkeypatch.setattr(chat, "_reply", forbidden)
        await chat.receive_text(message(answer=answer))
        assert "الصورة" in replies[0]
    asyncio.run(scenario())


def test_photo_caption_edit_keeps_original_instructions(monkeypatch):
    async def scenario():
        captured = []
        async def mode(_):
            return "chat"
        async def create(_, prompt, references):
            captured.append((prompt, references))
        monkeypatch.setattr(chat, "_mode", mode)
        monkeypatch.setattr(chat, "_create_image", create)
        reference = ReferenceImage(b"x")
        await chat._handle_images(message(), "/edit   keep my spacing  ", (reference,))
        assert captured == [("  keep my spacing  ", (reference,))]
    asyncio.run(scenario())


def test_history_is_scoped_by_chat_and_topic():
    assert chat._history_key(message()) == "chat.history:42:0"
    assert chat._history_key(message(message_thread_id=3)) == "chat.history:42:3"
    assert chat._history_key(message(chat=SimpleNamespace(id=43))) == "chat.history:43:0"


def test_album_accepts_image_documents_not_only_photos(monkeypatch):
    async def scenario():
        refs, results = [], []
        async def immediate(_):
            return
        async def ready(_):
            return True
        async def mode(_):
            return "vision"
        async def photo(_):
            refs.append("photo")
            return ReferenceImage(b"photo")
        async def document(_):
            refs.append("document")
            return ReferenceImage(b"document")
        async def handle(_, caption, images):
            results.append((caption, images))
        monkeypatch.setattr(chat.asyncio, "sleep", immediate)
        monkeypatch.setattr(chat, "_ensure_ready", ready)
        monkeypatch.setattr(chat, "_mode", mode)
        monkeypatch.setattr(chat, "_photo_ref", photo)
        monkeypatch.setattr(chat, "_file_ref", document)
        monkeypatch.setattr(chat, "_handle_images", handle)
        monkeypatch.setattr(chat, "_orchestrator", SimpleNamespace(settings=SimpleNamespace(
            image_max_reference_images=10, chat_max_images=3)))
        monkeypatch.setattr(chat, "_album_messages", {"album": [
            message(message_id=1, caption="question", photo=[1]),
            message(message_id=2, caption=None, photo=None, document=object()),
        ]})
        monkeypatch.setattr(chat, "_album_tasks", {})
        await chat._flush_album("album")
        assert refs == ["photo", "document"]
        assert len(results[0][1]) == 2
        assert not chat._album_messages
    asyncio.run(scenario())


def test_download_rejects_large_stream_even_with_missing_declared_size(monkeypatch):
    async def scenario():
        async def download(_, destination):
            destination.write(b"a" * (1024 * 1024))
            destination.write(b"x")
        monkeypatch.setattr(chat, "_orchestrator", SimpleNamespace(settings=SimpleNamespace(image_max_upload_mb=1)))
        import pytest
        with pytest.raises(ValueError):
            await chat._download(message(bot=SimpleNamespace(download=download)), "file")
    asyncio.run(scenario())
