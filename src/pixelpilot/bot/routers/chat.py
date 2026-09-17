from __future__ import annotations

from io import BytesIO
from typing import Any

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from pixelpilot.bot.callbacks import safe_callback_answer
from pixelpilot.bot.keyboards import main_menu
from pixelpilot.domain import InstancePhase, MediaInput, UserInput
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
    _history.append(user_message)
    trimmed = _trim_history(_history, orch().settings.chat_history_messages)
    _history[:] = trimmed

    status = await message.answer("⏳ جاري المعالجة...")
    try:
        result = await orch().chat(history_snapshot())
    except Exception as exc:
        if _history and _history[-1] is user_message:
            _history.pop()
        await status.edit_text(f"❌ تعذر إكمال الطلب:\n{exc}")
        return

    _history.append({"role": "assistant", "content": result.text})
    _history[:] = _trim_history(_history, orch().settings.chat_history_messages)
    try:
        await status.delete()
    except Exception:
        pass
    await _deliver_text(message, result.text)


@router.message(Command("new"))
async def new_chat_command(message: Message) -> None:
    clear_history()
    await message.answer("🧹 بدأت محادثة جديدة. أرسل نصًا أو صورة أو تسجيلًا صوتيًا.")


@router.callback_query(lambda q: q.data == "chat:new")
async def new_chat_callback(callback: CallbackQuery) -> None:
    clear_history()
    await safe_callback_answer(callback, "تم مسح سياق المحادثة")
    await callback.message.edit_text(
        "🧹 <b>محادثة جديدة</b>\n\nأرسل نصًا أو صورة أو تسجيلًا صوتيًا مباشرة.",
        reply_markup=main_menu(),
    )


@router.callback_query(lambda q: q.data == "chat:help")
async def chat_help(callback: CallbackQuery) -> None:
    await safe_callback_answer(callback)
    await callback.message.edit_text(
        "💬 <b>استخدام PixelPilot</b>\n\n"
        "أرسل رسالتك للبوت مباشرة:\n"
        "• نص عادي\n"
        "• صورة، ومعها تعليق اختياري\n"
        "• Voice أو ملف صوتي، ومعه تعليق اختياري\n\n"
        "المحتوى يذهب للموديل كما أرسلته، بدون System Prompt أو تعليمات داخلية من PixelPilot.\n"
        "استخدم /new أو زر «محادثة جديدة» لمسح السياق الحالي.",
        reply_markup=main_menu(),
    )


@router.message(F.photo)
async def receive_photo(message: Message) -> None:
    if not await _ensure_ready(message):
        return
    try:
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


@router.message(F.document)
async def receive_document(message: Message) -> None:
    mime = (message.document.mime_type or "").lower()
    if not (mime.startswith("image/") or mime.startswith("audio/")):
        return
    if not await _ensure_ready(message):
        return
    try:
        data = await _download_telegram_file(message, message.document.file_id)
        _check_media_size(data)
    except Exception as exc:
        await message.answer(f"❌ تعذر قراءة الملف: {exc}")
        return
    kind = "image" if mime.startswith("image/") else "audio"
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
