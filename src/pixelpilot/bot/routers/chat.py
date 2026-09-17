from __future__ import annotations

from io import BytesIO
from typing import Any

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from pixelpilot.bot.callbacks import safe_callback_answer
from pixelpilot.bot.keyboards import main_menu
from pixelpilot.domain import InstancePhase, MediaInput, UserInput
from pixelpilot.services.assistant_runtime import chat_with_options
from pixelpilot.services.assistant_settings import (
    context_policy,
    effective_system_prompt,
    generation_params,
)
from pixelpilot.services.orchestrator import Orchestrator

router = Router(name="chat")
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
        await message.answer(chunk, parse_mode=None)


async def _handle_input(message: Message, user_input: UserInput) -> None:
    if not await _ensure_ready(message):
        return

    user_message = user_input.to_openai_message()
    context_enabled, max_messages = await context_policy(
        orch().db,
        default_messages=orch().settings.chat_history_messages,
    )

    if context_enabled:
        _history.append(user_message)
        _history[:] = _trim_history(_history, max_messages)
        conversation = history_snapshot()
    else:
        conversation = [user_message]

    system_prompt = (await effective_system_prompt(orch().db)).strip()
    outbound = list(conversation)
    if system_prompt:
        outbound.insert(0, {"role": "system", "content": system_prompt})

    generation = await generation_params(
        orch().db,
        max_output_tokens=orch().settings.model_max_output_tokens,
    )

    status = await message.answer("⏳ جاري المعالجة...")
    try:
        result = await chat_with_options(orch(), outbound, generation=generation)
    except Exception as exc:
        if context_enabled and _history and _history[-1] is user_message:
            _history.pop()
        await status.edit_text(f"❌ تعذر إكمال الطلب:\n{exc}")
        return

    if context_enabled:
        _history.append({"role": "assistant", "content": result.text})
        _history[:] = _trim_history(_history, max_messages)
    try:
        await status.delete()
    except Exception:
        pass
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
