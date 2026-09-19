from __future__ import annotations

import logging
from io import BytesIO
from time import monotonic
from typing import Any

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from pixelpilot.bot.callbacks import safe_callback_answer
from pixelpilot.bot.keyboards import main_menu
from pixelpilot.bot.rich_ui import response_card
from pixelpilot.domain import InstancePhase, MediaInput, UserInput
from pixelpilot.services.assistant_runtime import stream_chat_with_options
from pixelpilot.services.assistant_settings import (
    context_policy,
    effective_system_prompt,
    generation_params,
)
from pixelpilot.services.orchestrator import Orchestrator

router = Router(name="chat")
logger = logging.getLogger(__name__)
_orchestrator: Orchestrator | None = None
_history: list[dict[str, Any]] = []


def configure(orchestrator: Orchestrator) -> None:
    global _orchestrator
    _orchestrator = orchestrator


def orch() -> Orchestrator:
    if _orchestrator is None:
        raise RuntimeError("Chat router not configured")
    return _orchestrator


def clear_history() -> None:
    _history.clear()


def history_snapshot() -> list[dict[str, Any]]:
    return list(_history)


def _trim_history(messages: list[dict[str, Any]], max_messages: int) -> list[dict[str, Any]]:
    trimmed = list(messages[-max_messages:])
    while trimmed and trimmed[0].get("role") == "assistant":
        trimmed.pop(0)
    return trimmed


async def _ensure_ready(message: Message) -> bool:
    phase = await orch().db.get("instance.phase", InstancePhase.NONE.value)
    if phase == InstancePhase.READY.value:
        return True
    await message.answer(
        "السيرفر غير جاهز الآن. استأجر سيرفر أو شغّل السيرفر الحالي أولًا.",
        reply_markup=main_menu(),
    )
    return False


async def _download_telegram_file(message: Message, file_id: str) -> bytes:
    buffer = BytesIO()
    await message.bot.download(file_id, destination=buffer)
    return buffer.getvalue()


def _check_declared_size(file_size: int | None) -> None:
    if not file_size:
        return
    max_bytes = orch().settings.chat_max_media_mb * 1024 * 1024
    if int(file_size) > max_bytes:
        raise ValueError(
            f"حجم الملف أكبر من الحد المسموح ({orch().settings.chat_max_media_mb} MB)."
        )


def _check_media_size(data: bytes) -> None:
    max_bytes = orch().settings.chat_max_media_mb * 1024 * 1024
    if len(data) > max_bytes:
        raise ValueError(
            f"حجم الملف أكبر من الحد المسموح ({orch().settings.chat_max_media_mb} MB)."
        )


async def _deliver_text(message: Message, text: str) -> None:
    remaining = text
    while remaining:
        if len(remaining) <= 4000:
            chunk, remaining = remaining, ""
        else:
            cut = remaining.rfind("\n", 0, 4000)
            if cut < 1000:
                cut = 4000
            chunk, remaining = remaining[:cut], remaining[cut:]
            remaining = remaining.lstrip("\n")

        # Prefer Telegram's native Rich Message renderer for completed model
        # output. If a model returns malformed/incomplete Markdown (for
        # example because a long code block was split), fall back to plain
        # text rather than losing the answer.
        try:
            await message.bot.send_rich_message(
                chat_id=message.chat.id,
                message_thread_id=message.message_thread_id,
                rich_message=response_card(chunk),
            )
        except Exception:
            await message.answer(chunk, parse_mode=None)


def _draft_preview(text: str, limit: int = 4000) -> str:
    """Keep Telegram draft updates inside the 4096-character message limit."""
    if len(text) <= limit:
        return text
    return "…" + text[-(limit - 1):]


async def _prepare_audio_input(message: Message, user_input: UserInput) -> UserInput:
    audio_parts = [item for item in user_input.media if item.kind == "audio"]
    if not audio_parts:
        return user_input

    status = await message.answer("🎧 جاري فهم التسجيل الصوتي...")
    try:
        transcripts = [
            await orch().transcribe_audio(item.data, mime_type=item.mime_type)
            for item in audio_parts
        ]
    finally:
        try:
            await status.delete()
        except Exception:
            pass

    text_parts = [text.strip() for text in transcripts if text.strip()]
    if user_input.text and user_input.text.strip():
        text_parts.append(user_input.text.strip())
    remaining_media = tuple(item for item in user_input.media if item.kind != "audio")
    return UserInput(
        text="\n\n".join(text_parts) if text_parts else None,
        media=remaining_media,
    )


async def _handle_input(message: Message, user_input: UserInput) -> None:
    if not await _ensure_ready(message):
        return

    try:
        user_input = await _prepare_audio_input(message, user_input)
    except Exception as exc:
        await message.answer(f"❌ تعذر فهم التسجيل الصوتي:\n{exc}")
        return

    user_message = user_input.to_openai_message()
    context_enabled, max_messages = await context_policy(
        orch().db,
        default_messages=orch().settings.chat_history_messages,
    )

    has_video = any(media.kind == "video" for media in user_input.media)

    if context_enabled:
        # Video consumes a large multimodal token budget. Do not prepend old
        # turns to a fresh video request; otherwise a perfectly valid video
        # can exceed the 8K model context before generation even starts.
        if has_video:
            _history.clear()
        _history.append(user_message)
        _history[:] = _trim_history(_history, max_messages)
        conversation = history_snapshot()
    else:
        conversation = [user_message]

    system_prompt = (await effective_system_prompt(orch().db)).strip()
    outbound = list(conversation)
    if system_prompt:
        # Qwen2.5-Omni's official serving examples use typed text content for
        # the system turn. Use the same form so profile prompts are applied
        # unambiguously on multimodal and text-only requests.
        outbound.insert(
            0,
            {
                "role": "system",
                "content": [{"type": "text", "text": system_prompt}],
            },
        )

    generation = await generation_params(
        orch().db,
        max_output_tokens=orch().settings.model_max_output_tokens,
    )

    # Telegram Bot API 10.1 drafts let the user see the response while the
    # model is generating it. Drafts are private-chat only; other chat types
    # fall back to the classic processing message.
    draft_id = max(1, int(message.message_id))
    draft_enabled = message.chat.type == ChatType.PRIVATE
    status: Message | None = None
    if draft_enabled:
        try:
            await message.bot.send_message_draft(
                chat_id=message.chat.id,
                message_thread_id=message.message_thread_id,
                draft_id=draft_id,
                text="",
                parse_mode=None,
            )
        except Exception:
            logger.exception("Telegram message draft could not be started; falling back")
            draft_enabled = False
    if not draft_enabled:
        status = await message.answer("⏳ جاري المعالجة...")

    last_draft_at = 0.0
    last_draft_len = 0

    async def on_partial(partial: str) -> None:
        nonlocal draft_enabled, last_draft_at, last_draft_len
        if not draft_enabled or not partial:
            return

        now = monotonic()
        # Avoid hammering Telegram for every model token while still keeping
        # the animation visibly live. Large jumps bypass the time throttle.
        if now - last_draft_at < 0.30 and len(partial) - last_draft_len < 48:
            return

        try:
            await message.bot.send_message_draft(
                chat_id=message.chat.id,
                message_thread_id=message.message_thread_id,
                draft_id=draft_id,
                text=_draft_preview(partial),
                parse_mode=None,
            )
            last_draft_at = now
            last_draft_len = len(partial)
        except Exception:
            logger.exception("Telegram draft update failed; finishing response normally")
            draft_enabled = False

    try:
        result = await stream_chat_with_options(
            orch(),
            outbound,
            generation=generation,
            on_partial=on_partial,
        )
    except Exception as exc:
        if context_enabled and _history and _history[-1] is user_message:
            _history.pop()
        if status is not None:
            await status.edit_text(f"❌ تعذر إكمال الطلب:\n{exc}")
        else:
            await message.answer(f"❌ تعذر إكمال الطلب:\n{exc}")
        return

    if context_enabled:
        _history.append({"role": "assistant", "content": result.text})
        _history[:] = _trim_history(_history, max_messages)

    if status is not None:
        try:
            await status.delete()
        except Exception:
            pass

    # Sending the persistent final message dismisses Telegram's ephemeral
    # draft automatically. Long answers are still split safely as before.
    await _deliver_text(message, result.text)


@router.message(Command("new"))
async def new_chat_command(message: Message) -> None:
    clear_history()
    await message.answer("🧹 بدأت محادثة جديدة. أرسل نصًا أو صورة أو صوتًا أو فيديو.")


@router.callback_query(lambda q: q.data == "chat:new")
async def new_chat_callback(callback: CallbackQuery) -> None:
    clear_history()
    await safe_callback_answer(callback, "تم بدء محادثة جديدة")
    await callback.message.edit_text(
        "🧹 <b>محادثة جديدة</b>\n\nأرسل نصًا أو صورة أو صوتًا أو فيديو.",
        reply_markup=main_menu(),
    )


@router.callback_query(lambda q: q.data == "chat:help")
async def chat_help(callback: CallbackQuery) -> None:
    await safe_callback_answer(callback)
    await callback.message.edit_text(
        "💬 <b>طريقة الاستخدام</b>\n\n"
        "أرسل للبوت مباشرة:\n"
        "• رسالة نصية\n"
        "• صورة، ويمكنك إضافة تعليق معها\n"
        "• تسجيلًا صوتيًا أو ملفًا صوتيًا\n"
        "• فيديو، ويمكنك إضافة تعليق معه\n\n"
        "لبدء محادثة من جديد استخدم /new أو زر «محادثة جديدة».",
        reply_markup=main_menu(),
    )


@router.message(F.photo)
async def receive_photo(message: Message) -> None:
    if not await _ensure_ready(message):
        return
    try:
        _check_declared_size(message.photo[-1].file_size)
        data = await _download_telegram_file(message, message.photo[-1].file_id)
        _check_media_size(data)
    except Exception as exc:
        await message.answer(f"❌ تعذر قراءة الصورة: {exc}")
        return
    await _handle_input(
        message,
        UserInput(
            text=message.caption,
            media=(MediaInput(kind="image", data=data, mime_type="image/jpeg"),),
        ),
    )


@router.message(F.voice)
async def receive_voice(message: Message) -> None:
    if not await _ensure_ready(message):
        return
    try:
        _check_declared_size(message.voice.file_size)
        data = await _download_telegram_file(message, message.voice.file_id)
        _check_media_size(data)
    except Exception as exc:
        await message.answer(f"❌ تعذر قراءة التسجيل: {exc}")
        return
    await _handle_input(
        message,
        UserInput(
            text=message.caption,
            media=(
                MediaInput(
                    kind="audio",
                    data=data,
                    mime_type=message.voice.mime_type or "audio/ogg",
                ),
            ),
        ),
    )


@router.message(F.audio)
async def receive_audio(message: Message) -> None:
    if not await _ensure_ready(message):
        return
    try:
        _check_declared_size(message.audio.file_size)
        data = await _download_telegram_file(message, message.audio.file_id)
        _check_media_size(data)
    except Exception as exc:
        await message.answer(f"❌ تعذر قراءة الملف الصوتي: {exc}")
        return
    await _handle_input(
        message,
        UserInput(
            text=message.caption,
            media=(
                MediaInput(
                    kind="audio",
                    data=data,
                    mime_type=message.audio.mime_type or "audio/mpeg",
                ),
            ),
        ),
    )


@router.message(F.video)
async def receive_video(message: Message) -> None:
    if not await _ensure_ready(message):
        return
    try:
        _check_declared_size(message.video.file_size)
        data = await _download_telegram_file(message, message.video.file_id)
        _check_media_size(data)
    except Exception as exc:
        await message.answer(f"❌ تعذر قراءة الفيديو: {exc}")
        return
    await _handle_input(
        message,
        UserInput(
            text=message.caption,
            media=(
                MediaInput(
                    kind="video",
                    data=data,
                    mime_type=message.video.mime_type or "video/mp4",
                ),
            ),
        ),
    )


@router.message(F.video_note)
async def receive_video_note(message: Message) -> None:
    if not await _ensure_ready(message):
        return
    try:
        _check_declared_size(message.video_note.file_size)
        data = await _download_telegram_file(message, message.video_note.file_id)
        _check_media_size(data)
    except Exception as exc:
        await message.answer(f"❌ تعذر قراءة الفيديو: {exc}")
        return
    await _handle_input(
        message,
        UserInput(
            media=(MediaInput(kind="video", data=data, mime_type="video/mp4"),),
        ),
    )


@router.message(F.document)
async def receive_document(message: Message) -> None:
    mime = (message.document.mime_type or "").lower()
    if not (
        mime.startswith("image/")
        or mime.startswith("audio/")
        or mime.startswith("video/")
    ):
        return
    if not await _ensure_ready(message):
        return
    try:
        _check_declared_size(message.document.file_size)
        data = await _download_telegram_file(message, message.document.file_id)
        _check_media_size(data)
    except Exception as exc:
        await message.answer(f"❌ تعذر قراءة الملف: {exc}")
        return
    if mime.startswith("image/"):
        kind = "image"
    elif mime.startswith("video/"):
        kind = "video"
    else:
        kind = "audio"
    await _handle_input(
        message,
        UserInput(
            text=message.caption,
            media=(MediaInput(kind=kind, data=data, mime_type=mime),),
        ),
    )


@router.message(F.text)
async def receive_text(message: Message) -> None:
    text = message.text or ""
    if not text or text.startswith("/"):
        return
    await _handle_input(message, UserInput(text=text))
