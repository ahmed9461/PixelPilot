from __future__ import annotations

import asyncio
import logging
from io import BytesIO

from aiogram import F, Router
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from pixelpilot.bot.callbacks import safe_callback_answer
from pixelpilot.bot.keyboards import main_menu
from pixelpilot.domain import InstancePhase, ReferenceImage
from pixelpilot.services.image_settings import get_state
from pixelpilot.services.orchestrator import Orchestrator


router = Router(name="images")
logger = logging.getLogger(__name__)
_orchestrator: Orchestrator | None = None

_album_messages: dict[str, list[Message]] = {}
_album_tasks: dict[str, asyncio.Task[None]] = {}


def configure(orchestrator: Orchestrator) -> None:
    global _orchestrator
    _orchestrator = orchestrator


def orch() -> Orchestrator:
    if _orchestrator is None:
        raise RuntimeError("Image router not configured")
    return _orchestrator


async def _ensure_ready(message: Message) -> bool:
    phase = await orch().db.get("instance.phase", InstancePhase.NONE.value)
    if phase == InstancePhase.READY.value:
        return True
    await message.answer(
        "السيرفر غير جاهز الآن. استأجر سيرفر أو شغّل السيرفر الحالي أولًا.",
        reply_markup=main_menu(),
    )
    return False


def _check_declared_size(file_size: int | None) -> None:
    if not file_size:
        return
    max_bytes = orch().settings.image_max_upload_mb * 1024 * 1024
    if int(file_size) > max_bytes:
        raise ValueError(
            f"حجم الصورة أكبر من الحد المسموح ({orch().settings.image_max_upload_mb} MB)."
        )


def _check_media_size(data: bytes) -> None:
    max_bytes = orch().settings.image_max_upload_mb * 1024 * 1024
    if len(data) > max_bytes:
        raise ValueError(
            f"حجم الصورة أكبر من الحد المسموح ({orch().settings.image_max_upload_mb} MB)."
        )


async def _download_telegram_file(message: Message, file_id: str) -> bytes:
    buffer = BytesIO()
    await message.bot.download(file_id, destination=buffer)
    data = buffer.getvalue()
    _check_media_size(data)
    return data


async def _generate(
    message: Message,
    *,
    prompt: str,
    references: tuple[ReferenceImage, ...] = (),
) -> None:
    if not await _ensure_ready(message):
        return
    if not prompt.strip():
        await message.answer("اكتب وصف الصورة أو تعليمات التعديل مع الصورة.")
        return

    image_settings = await get_state(orch().db)
    status_text = (
        "🎨 جاري تعديل الصورة..."
        if references
        else "🎨 جاري إنشاء الصورة..."
    )
    status = await message.answer(status_text)

    try:
        result = await orch().generate_image(
            prompt,
            width=image_settings.width,
            height=image_settings.height,
            steps=image_settings.steps,
            reference_images=references,
        )
    except Exception as exc:
        logger.exception("Image request failed")
        await status.edit_text(f"❌ تعذر إنشاء الصورة:\n{exc}")
        return

    try:
        await status.delete()
    except Exception:
        pass

    caption = (
        f"✅ تم — {result.width}×{result.height}\n"
        f"🎲 Seed: <code>{result.seed}</code>"
    )
    await message.answer_document(
        BufferedInputFile(result.data, filename=f"pixelpilot-{result.seed}.png"),
        caption=caption,
        reply_markup=main_menu(),
    )


async def _photo_to_reference(message: Message) -> ReferenceImage:
    photo = message.photo[-1]
    _check_declared_size(photo.file_size)
    data = await _download_telegram_file(message, photo.file_id)
    return ReferenceImage(data=data, mime_type="image/jpeg")


async def _flush_album(media_group_id: str) -> None:
    try:
        await asyncio.sleep(0.9)
        messages = _album_messages.pop(media_group_id, [])
        if not messages:
            return
        messages.sort(key=lambda item: item.message_id)
        anchor = messages[0]
        max_refs = orch().settings.image_max_reference_images
        if len(messages) > max_refs:
            await anchor.answer(f"الحد الأقصى للصور المرجعية هو {max_refs}.")
            return

        prompt = next(
            (item.caption for item in messages if item.caption is not None and item.caption.strip()),
            None,
        )
        if prompt is None:
            await anchor.answer(
                "أرسل الصور كألبوم مع كتابة تعليمات التعديل في وصف إحدى الصور."
            )
            return

        references: list[ReferenceImage] = []
        try:
            for item in messages:
                references.append(await _photo_to_reference(item))
        except Exception as exc:
            await anchor.answer(f"❌ تعذر قراءة إحدى الصور: {exc}")
            return

        await _generate(anchor, prompt=prompt, references=tuple(references))
    finally:
        _album_tasks.pop(media_group_id, None)


@router.callback_query(lambda q: q.data == "chat:help")
async def chat_help(callback: CallbackQuery) -> None:
    await safe_callback_answer(callback)
    await callback.message.edit_text(
        "🎨 <b>طريقة الاستخدام</b>\n\n"
        "• لإنشاء صورة: أرسل وصفك كنص عادي.\n"
        "• لتعديل صورة: أرسل الصورة واكتب تعليمات التعديل في الوصف.\n"
        "• يمكنك إرسال ألبوم يصل إلى 10 صور مرجعية مع تعليماتك.\n"
        "• من «إعدادات الصور» تستطيع تغيير النسبة والجودة وعدد خطوات التوليد.\n\n"
        "لا يتم إضافة شخصية أو مشاعر أو برومت مخفي إلى طلبك.",
        reply_markup=main_menu(),
    )


@router.message(F.photo)
async def receive_photo(message: Message) -> None:
    if message.media_group_id:
        group_id = str(message.media_group_id)
        _album_messages.setdefault(group_id, []).append(message)
        if group_id not in _album_tasks:
            _album_tasks[group_id] = asyncio.create_task(
                _flush_album(group_id),
                name=f"pixelpilot-album-{group_id}",
            )
        return

    if not await _ensure_ready(message):
        return
    if message.caption is None or not message.caption.strip():
        await message.answer(
            "أرسل الصورة مع تعليمات التعديل في وصف الصورة."
        )
        return
    try:
        reference = await _photo_to_reference(message)
    except Exception as exc:
        await message.answer(f"❌ تعذر قراءة الصورة: {exc}")
        return
    await _generate(message, prompt=message.caption, references=(reference,))


@router.message(F.document)
async def receive_document(message: Message) -> None:
    mime = (message.document.mime_type or "").lower()
    if not mime.startswith("image/"):
        return
    if not await _ensure_ready(message):
        return
    if message.caption is None or not message.caption.strip():
        await message.answer(
            "أرسل ملف الصورة مع تعليمات التعديل في وصف الملف."
        )
        return
    try:
        _check_declared_size(message.document.file_size)
        data = await _download_telegram_file(message, message.document.file_id)
    except Exception as exc:
        await message.answer(f"❌ تعذر قراءة الصورة: {exc}")
        return

    await _generate(
        message,
        prompt=message.caption,
        references=(ReferenceImage(data=data, mime_type=mime or "image/png"),),
    )


@router.message(F.text)
async def receive_text(message: Message) -> None:
    prompt = message.text
    if not prompt or prompt.startswith("/"):
        return
    await _generate(message, prompt=prompt)
