"""Owner-only Telegram chat, image understanding and image editing router."""
from __future__ import annotations

import asyncio
import logging
from html import escape

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from pixelpilot.bot.callbacks import safe_callback_answer
from pixelpilot.bot.keyboards import main_menu
from pixelpilot.domain import InstancePhase, ReferenceImage
from pixelpilot.contracts import BoundedBuffer, MAX_TOTAL_IMAGE_BYTES, telegram_chunks
from pixelpilot.services.image_settings import get_state
from pixelpilot.services.orchestrator import Orchestrator, OrchestratorError


router = Router(name="multimodal")
logger = logging.getLogger(__name__)
_orchestrator: Orchestrator | None = None
_album_messages: dict[str, list[Message]] = {}
_album_tasks: dict[str, asyncio.Task[None]] = {}

MODES = {"chat", "generate", "edit", "vision"}


def configure(orchestrator: Orchestrator) -> None:
    global _orchestrator
    _orchestrator = orchestrator


def orch() -> Orchestrator:
    if _orchestrator is None:
        raise RuntimeError("Multimodal router not configured")
    return _orchestrator


def _scope(message: Message) -> str:
    return f"{message.chat.id}:{getattr(message, 'message_thread_id', None) or 0}"


def _history_key(message: Message) -> str:
    return "chat.history:" + _scope(message)


async def _mode(message: Message) -> str:
    value = await orch().db.get("chat.mode:" + _scope(message), "chat")
    return value if value in MODES else "chat"


async def _ensure_ready(message: Message) -> bool:
    if await orch().db.get("instance.phase", InstancePhase.NONE.value) == InstancePhase.READY.value:
        return True
    await message.answer(
        "السيرفر غير جاهز الآن. استأجر سيرفر أو شغّل السيرفر الحالي أولًا.",
        reply_markup=main_menu(),
    )
    return False


def _size_ok(size: int | None) -> None:
    maximum = orch().settings.image_max_upload_mb * 1024 * 1024
    if size and size > maximum:
        raise ValueError(f"حجم الصورة يتجاوز {orch().settings.image_max_upload_mb} MB")


async def _download(message: Message, file_id: str) -> bytes:
    with BoundedBuffer(orch().settings.image_max_upload_mb * 1024 * 1024) as buffer:
        await message.bot.download(file_id, destination=buffer)
        return buffer.getvalue()


async def _photo_ref(message: Message) -> ReferenceImage:
    photo = message.photo[-1]
    _size_ok(photo.file_size)
    return ReferenceImage(data=await _download(message, photo.file_id), mime_type="image/jpeg")


async def _file_ref(message: Message) -> ReferenceImage:
    doc = message.document
    _size_ok(doc.file_size)
    return ReferenceImage(
        data=await _download(message, doc.file_id),
        mime_type=doc.mime_type or "image/png",
    )


async def _create_image(
    message: Message, prompt: str, references: tuple[ReferenceImage, ...] = (),
) -> None:
    if not await _ensure_ready(message):
        return
    if not prompt.strip():
        await message.answer("أرسل وصفًا لإنشاء صورة، أو تعليمات تعديل مع الصورة.")
        return

    settings = await get_state(orch().db)
    status = await message.answer("🎨 جاري تعديل الصورة..." if references else "🎨 جاري إنشاء الصورة...")
    try:
        result = await orch().generate_image(
            prompt,
            width=settings.width,
            height=settings.height,
            steps=settings.steps,
            reference_images=references,
            enhance_prompt=settings.enhance_prompt,
        )
    except OrchestratorError as exc:
        await status.edit_text("⚠️ " + escape(str(exc)))
        return
    except Exception:
        logger.exception("Image generation/editing failed")
        await status.edit_text(
            "❌ تعذر تنفيذ طلب الصورة. تأكد من جاهزية السيرفر والذاكرة ثم جرّب مرة أخرى."
        )
        return
    try:
        await status.delete()
    except Exception:
        pass
    note = "✨ تم تحسين البرومت" if result.prompt_enhanced else (
        "⚠️ استخدم البرومت الأصلي لتعذر التحسين" if result.enhancer_fallback else ""
    )
    await message.answer_document(
        BufferedInputFile(result.data, filename=f"pixelpilot-{result.seed}.png"),
        caption=f"✅ تم — {result.width}×{result.height}\nSeed: <code>{result.seed}</code>\n{note}",
        reply_markup=main_menu(),
    )


async def _reply(message: Message, prompt: str, images: tuple[ReferenceImage, ...] = ()) -> None:
    if not await _ensure_ready(message):
        return
    if len(images) > orch().settings.chat_max_images:
        await message.answer(
            f"يمكن تحليل {orch().settings.chat_max_images} صور كحد أقصى في رسالة واحدة."
        )
        return
    status = await message.answer("👁️ جاري فهم الصورة..." if images else "🧠 جاري التفكير...")
    try:
        answer = await orch().chat(prompt, reference_images=images, history_key=_history_key(message))
    except OrchestratorError as exc:
        await status.edit_text("⚠️ " + escape(str(exc)))
        return
    except Exception:
        logger.exception("Multimodal chat failed")
        await status.edit_text(
            "❌ تعذر الرد الآن. تأكد أن محرك الدردشة جاهز، ثم أعد المحاولة."
        )
        return
    try:
        await status.delete()
    except Exception:
        pass
    # Plain text avoids model-produced HTML; UTF-16 bounds also cover emoji.
    for chunk in telegram_chunks(answer):
        await message.answer(chunk, parse_mode=None)


def _edit_caption(caption: str | None) -> str | None:
    raw = caption or ""
    if raw == "/edit":
        return ""
    if raw.startswith("/edit "):
        return raw[6:]
    return None


async def _handle_images(
    message: Message, caption: str | None, images: tuple[ReferenceImage, ...],
) -> None:
    explicit_edit = _edit_caption(caption)
    mode = await _mode(message)
    if explicit_edit is not None or mode == "edit":
        prompt = explicit_edit if explicit_edit is not None else (caption or "")
        if not prompt:
            await message.answer("اكتب تعليمات التعديل في وصف الصورة، مثل: غيّر الخلفية إلى حديقة.")
            return
        await _create_image(message, prompt, images)
        return
    await _reply(message, caption if caption and caption.strip() else "اشرح لي ما الذي يظهر في الصورة بالتفصيل.", images)


async def _flush_album(group_id: str) -> None:
    try:
        await asyncio.sleep(0.9)
        messages = sorted(_album_messages.pop(group_id, []), key=lambda x: x.message_id)
        if not messages:
            return
        anchor = messages[0]
        max_refs = orch().settings.image_max_reference_images
        if len(messages) > max_refs:
            await anchor.answer(f"الحد الأقصى لألبوم الصور هو {max_refs}.")
            return
        caption = next((m.caption for m in messages if m.caption and m.caption.strip()), None)
        edit_mode = _edit_caption(caption) is not None or await _mode(anchor) == "edit"
        limit = max_refs if edit_mode else orch().settings.chat_max_images
        if len(messages) > limit:
            await anchor.answer(f"هذا الوضع يدعم حتى {limit} صور في المرة الواحدة.")
            return
        if not await _ensure_ready(anchor):
            return
        try:
            references_list: list[ReferenceImage] = []
            total_bytes = 0
            for item in messages:
                reference = await (_photo_ref(item) if item.photo else _file_ref(item))
                total_bytes += len(reference.data)
                if total_bytes > MAX_TOTAL_IMAGE_BYTES:
                    raise ValueError("Combined images exceed 50 MB")
                references_list.append(reference)
            references = tuple(references_list)
        except Exception:
            logger.exception("Telegram album download failed")
            await anchor.answer("❌ تعذر تحميل الصور المرجعية.")
            return
        await _handle_images(anchor, caption, references)
    finally:
        # A newer debounce task may already have replaced this cancelled task.
        if _album_tasks.get(group_id) is asyncio.current_task():
            _album_tasks.pop(group_id, None)


async def _queue_album(message: Message) -> None:
    group_id = f"{message.chat.id}:{message.media_group_id}"
    if group_id in _album_tasks and group_id not in _album_messages:
        await message.answer("بدأت معالجة الألبوم السابق؛ أرسل الصور المتأخرة كألبوم جديد.")
        return
    if group_id not in _album_messages and len(_album_messages) >= 16:
        await message.answer("توجد ألبومات كثيرة قيد المعالجة؛ أعد المحاولة بعد اكتمالها.")
        return
    batch = _album_messages.setdefault(group_id, [])
    if len(batch) <= orch().settings.image_max_reference_images:
        batch.append(message)
    previous = _album_tasks.get(group_id)
    if previous is not None:
        previous.cancel()
    _album_tasks[group_id] = asyncio.create_task(_flush_album(group_id), name="pixelpilot-album")


async def shutdown() -> None:
    tasks = tuple(_album_tasks.values())
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    _album_tasks.clear()
    _album_messages.clear()


@router.callback_query(lambda q: q.data and q.data.startswith("chat:mode:"))
async def set_mode(callback: CallbackQuery) -> None:
    value = callback.data.rsplit(":", 1)[-1]
    if value not in MODES:
        await safe_callback_answer(callback, "وضع غير صالح", show_alert=True)
        return
    await orch().db.set("chat.mode:" + _scope(callback.message), value)
    await safe_callback_answer(callback, "تم اختيار الوضع")
    help_text = {
        "chat": "🧠 وضع الدردشة: أرسل أي سؤال، ويمكنك إرسال صورة لتحليلها.",
        "vision": "👁️ وضع فهم الصور: أرسل صورة مع سؤالك، أو أرسلها دون وصف لشرحها.",
        "generate": "🎨 وضع إنشاء الصور: أرسل وصفًا نصيًا وسيُنشئ صورة جديدة.",
        "edit": "🖌️ وضع تعديل الصور: أرسل الصورة مع وصف التعديل المطلوب.",
    }
    await callback.message.answer(help_text[value], reply_markup=main_menu())


@router.callback_query(lambda q: q.data == "chat:help")
async def chat_help(callback: CallbackQuery) -> None:
    await safe_callback_answer(callback)
    await callback.message.answer(
        "🧠 <b>طريقة الاستخدام</b>\n\n"
        "• أرسل نصًا للدردشة أو أرسل صورة لفهمها.\n"
        "• /image وصف — إنشاء صورة جديدة دون تغيير وضع الدردشة.\n"
        "• أرسل صورة ووصفها يبدأ بـ /edit لتعديلها.\n"
        "• يمكنك اختيار وضع تعديل الصور من القائمة.\n"
        "• /clear يمسح ذاكرة الدردشة النصية.\n"
        "• إعدادات الصور تتيح التحكم بالجودة والنسبة والخطوات.\n\n"
        "الصور لا تُحفظ في سجل المحادثة؛ يحفظ البوت نصوص آخر الرسائل فقط.",
        reply_markup=main_menu(),
    )


@router.message(F.text, Command("clear"))
async def clear_chat(message: Message) -> None:
    await orch().clear_chat_history(history_key=_history_key(message))
    await message.answer("🧹 تم مسح ذاكرة الدردشة النصية.", reply_markup=main_menu())


@router.callback_query(lambda q: q.data == "chat:clear")
async def clear_chat_button(callback: CallbackQuery) -> None:
    await safe_callback_answer(callback, "جاري مسح الذاكرة")
    await clear_chat(callback.message)


@router.message(F.text, Command("image"))
async def image_command(message: Message) -> None:
    prompt = (message.text or "").partition(" ")[2]
    await _create_image(message, prompt)


@router.message(F.text, Command("edit"))
async def edit_command(message: Message) -> None:
    prompt = (message.text or "").partition(" ")[2]
    replied = message.reply_to_message
    if not replied or not (replied.photo or (replied.document and (replied.document.mime_type or "").startswith("image/"))):
        await message.answer("ارسل الصورة مع وصف يبدأ بـ /edit أو رد على الصورة بأمر /edit التعليمات.")
        return
    if not prompt:
        await message.answer("اكتب تعليمات التعديل بعد /edit.")
        return
    try:
        reference = await (_photo_ref(replied) if replied.photo else _file_ref(replied))
    except Exception:
        await message.answer("تعذر قراءة الصورة التي تريد تعديلها.")
        return
    await _create_image(message, prompt, (reference,))


@router.message(F.photo)
async def receive_photo(message: Message) -> None:
    if message.media_group_id:
        await _queue_album(message)
        return
    if not await _ensure_ready(message):
        return
    try:
        reference = await _photo_ref(message)
    except Exception:
        logger.exception("Telegram photo download failed")
        await message.answer("❌ تعذر قراءة الصورة أو أنها أكبر من الحد المسموح.")
        return
    await _handle_images(message, message.caption, (reference,))


@router.message(F.document)
async def receive_document(message: Message) -> None:
    if not (message.document.mime_type or "").startswith("image/"):
        return
    if message.media_group_id:
        await _queue_album(message)
        return
    if not await _ensure_ready(message):
        return
    try:
        reference = await _file_ref(message)
    except Exception:
        logger.exception("Telegram document download failed")
        await message.answer("❌ تعذر قراءة ملف الصورة.")
        return
    await _handle_images(message, message.caption, (reference,))


@router.message(F.text)
async def receive_text(message: Message) -> None:
    prompt = message.text or ""
    if not prompt.strip() or prompt.startswith("/"):
        return
    mode = await _mode(message)
    if mode == "generate":
        await _create_image(message, prompt)
        return
    replied = message.reply_to_message
    if replied and (replied.photo or (replied.document and (replied.document.mime_type or "").startswith("image/"))):
        if not await _ensure_ready(message):
            return
        try:
            reference = await (_photo_ref(replied) if replied.photo else _file_ref(replied))
        except Exception:
            await message.answer("تعذر قراءة الصورة المرجعية؛ أعد إرسالها مع سؤالك.")
            return
        await _handle_images(message, prompt, (reference,))
    elif mode == "edit":
        await message.answer("أرسل الصورة مع تعليمات التعديل، أو رد على صورة سابقة بتعليماتك.")
    else:
        await _reply(message, prompt)
