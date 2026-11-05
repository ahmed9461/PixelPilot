"""Owner-only Telegram chat, image understanding and image editing router."""
from __future__ import annotations

import asyncio
import logging
from html import escape
from io import BytesIO

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from pixelpilot.bot.callbacks import safe_callback_answer, safe_edit_text
from pixelpilot.bot.keyboards import main_menu
from pixelpilot.bot.telegram_markdown import format_model_reply
from pixelpilot.domain import InstancePhase, ReferenceImage
from pixelpilot.services.image_settings import get_state
from pixelpilot.services.orchestrator import Orchestrator
from pixelpilot.services.vision_runtime import is_text_only_chat_model


router = Router(name="multimodal")
logger = logging.getLogger(__name__)
_orchestrator: Orchestrator | None = None
_album_messages: dict[str, list[Message]] = {}
_album_tasks: dict[str, asyncio.Task[None]] = {}

MODES = {"chat", "generate", "edit", "vision"}

def _error_text(exc: Exception) -> str:
    raw = str(exc).lower()
    if "out of memory" in raw: return "نفدت ذاكرة GPU. استخدم الجودة القياسية أو صورًا مرجعية أقل أو GPU أكبر."
    if "context" in raw or "too long" in raw: return "تجاوز الطلب حد السياق الآمن. قلّل النص أو عدد الصور."
    if "12000" in raw: return "حد الرسالة 12000 حرف؛ قسّمها إلى رسالتين."
    if "tls" in raw or "مشفر" in raw: return "تعذر التحقق من الاتصال المشفر بخادم GPU."
    if "failed to load" in raw or "model startup" in raw: return "فشل تحميل النموذج؛ افحص مساحة القرص والتنزيل واعتمادات العامل."
    if "timeout" in raw: return "انتهت مهلة المعالجة؛ قد يستمر العمل على GPU. افحص الحالة قبل إعادة الطلب."
    return "فشل الاتصال أو الاستدلال؛ افحص حالة السيرفر وسجلات العامل ثم أعد المحاولة."



def configure(orchestrator: Orchestrator) -> None:
    global _orchestrator
    _orchestrator = orchestrator


def orch() -> Orchestrator:
    if _orchestrator is None:
        raise RuntimeError("Multimodal router not configured")
    return _orchestrator


async def _mode() -> str:
    value = await orch().db.get("chat.mode", "chat")
    return value if value in MODES else "chat"


async def _ensure_ready(message: Message) -> bool:
    if await orch().db.get("instance.phase", InstancePhase.NONE.value) == InstancePhase.READY.value:
        return True
    await message.answer(
        "السيرفر غير جاهز الآن. استأجر سيرفر أو شغّل السيرفر الحالي أولًا.",
        reply_markup=main_menu(),
    )
    return False


async def _show_progress(status: Message) -> None:
    try:
        while True:
            await asyncio.sleep(5)
            try:
                info = await orch().inference_progress()
                p = info.get("progress", {})
                text = f"⏳ النموذج: {p.get('model') or 'Qwen'}\nالمرحلة: {p.get('stage', 'processing')}"
                if p.get('percent') is not None: text += f" — {p['percent']}%"
                if p.get('downloaded_bytes') is not None: text += f"\nالكاش: {p['downloaded_bytes']/1e9:.2f} GB"
                if p.get('total_bytes'): text += f" / {p['total_bytes']/1e9:.2f} GB"
                if p.get('mbps') is not None: text += f"\nسرعة نمو الكاش المقاسة: {p['mbps']} Mbps"
                if p.get('step') is not None: text += f"\nخطوة التوليد: {p['step']}/{p.get('steps', '?')}"
                await safe_edit_text(status, text, parse_mode=None)
            except Exception:
                pass
    except asyncio.CancelledError:
        return


def _size_ok(size: int | None) -> None:
    maximum = orch().settings.image_max_upload_mb * 1024 * 1024
    if size and size > maximum:
        raise ValueError(f"حجم الصورة يتجاوز {orch().settings.image_max_upload_mb} MB")


async def _download(message: Message, file_id: str) -> bytes:
    buffer = BytesIO()
    await message.bot.download(file_id, destination=buffer)
    data = buffer.getvalue()
    _size_ok(len(data))
    return data


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
    progress_task = asyncio.create_task(_show_progress(status))
    try:
        result = await orch().generate_image(
            prompt,
            width=settings.width,
            height=settings.height,
            steps=settings.steps,
            reference_images=references,
            enhance_prompt=settings.enhance_prompt,
        )
    except Exception as exc:
        progress_task.cancel()
        await asyncio.gather(progress_task, return_exceptions=True)
        logger.exception("Image generation/editing failed")
        await safe_edit_text(status,
            "❌ تعذر تنفيذ طلب الصورة. " + _error_text(exc)
        )
        return
    finally:
        progress_task.cancel()
        await asyncio.gather(progress_task, return_exceptions=True)
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
    if images and is_text_only_chat_model(orch().settings.chat_model_id):
        await message.answer("🧠 النموذج المجتمعي الحالي للدردشة النصية فقط؛ فهم الصور غير متاح في هذه التجربة. يمكنك استخدام /image أو /edit لإنشاء الصور وتعديلها.")
        return
    if len(images) > orch().settings.chat_max_images:
        await message.answer(
            f"يمكن تحليل {orch().settings.chat_max_images} صور كحد أقصى في رسالة واحدة."
        )
        return
    status = await message.answer("👁️ جاري فهم الصورة..." if images else "🧠 جاري التفكير...")
    try:
        answer = await orch().chat(prompt, reference_images=images)
    except Exception as exc:
        logger.exception("Multimodal chat failed")
        await safe_edit_text(status,
            "❌ تعذر الرد الآن. " + _error_text(exc)
        )
        return
    try:
        await status.delete()
    except Exception:
        pass
    # Convert model Markdown to Telegram entities; never parse untrusted HTML.
    # Split by Telegram UTF-16 limits, preserving formatting and emoji offsets.
    for chunk in format_model_reply(answer):
        try:
            await message.answer(chunk.text, entities=list(chunk.entities), parse_mode=None)
        except TelegramBadRequest as exc:
            # An unexpected entity error should not discard an otherwise valid reply.
            if "parse entities" not in str(exc).lower():
                raise
            logger.warning("Telegram rejected model formatting; sending plain text: %s", exc)
            await message.answer(chunk.text, parse_mode=None)


def _edit_caption(caption: str | None) -> str | None:
    raw = (caption or "").strip()
    if raw == "/edit":
        return ""
    if raw.split(" ", 1)[0].split("@", 1)[0] == "/edit":
        return raw.partition(" ")[2].strip()
    return None


async def _handle_images(
    message: Message, caption: str | None, images: tuple[ReferenceImage, ...],
) -> None:
    explicit_edit = _edit_caption(caption)
    mode = await _mode()
    if explicit_edit is not None or mode == "edit":
        prompt = explicit_edit if explicit_edit is not None else (caption or "").strip()
        if not prompt:
            await message.answer("اكتب تعليمات التعديل في وصف الصورة، مثل: غيّر الخلفية إلى حديقة.")
            return
        await _create_image(message, prompt, images)
        return
    await _reply(message, (caption or "").strip() or "اشرح لي ما الذي يظهر في الصورة بالتفصيل.", images)


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
        edit_mode = _edit_caption(caption) is not None or await _mode() == "edit"
        limit = max_refs if edit_mode else orch().settings.chat_max_images
        if len(messages) > limit:
            await anchor.answer(f"هذا الوضع يدعم حتى {limit} صور في المرة الواحدة.")
            return
        try:
            references = tuple([await (_photo_ref(m) if m.photo else _file_ref(m)) for m in messages])
        except Exception:
            logger.exception("Telegram album download failed")
            await anchor.answer("❌ تعذر تحميل الصور المرجعية.")
            return
        await _handle_images(anchor, caption, references)
    finally:
        _album_tasks.pop(group_id, None)


@router.callback_query(lambda q: q.data and q.data.startswith("chat:mode:"))
async def set_mode(callback: CallbackQuery) -> None:
    value = callback.data.rsplit(":", 1)[-1]
    if value not in MODES:
        await safe_callback_answer(callback, "وضع غير صالح", show_alert=True)
        return
    if value == "vision" and is_text_only_chat_model(orch().settings.chat_model_id):
        await safe_callback_answer(callback, "فهم الصور غير متاح مع نموذج الدردشة النصي الحالي", show_alert=True)
        return
    await orch().db.set("chat.mode", value)
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
        "• أرسل نصًا للدردشة. فهم الصور يتطلب نموذج دردشة متعدد الوسائط.\n"
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
    await orch().clear_chat_history()
    await message.answer("🧹 تم مسح ذاكرة الدردشة النصية.", reply_markup=main_menu())


@router.message(F.text, Command("image"))
async def image_command(message: Message) -> None:
    prompt = (message.text or "").partition(" ")[2].strip()
    await _create_image(message, prompt)


@router.message(F.text, Command("edit"))
async def edit_command(message: Message) -> None:
    prompt = (message.text or "").partition(" ")[2].strip()
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
        group_id = f"{message.chat.id}:{message.media_group_id}"
        _album_messages.setdefault(group_id, []).append(message)
        if group_id not in _album_tasks:
            _album_tasks[group_id] = asyncio.create_task(
                _flush_album(group_id), name=f"pixelpilot-album-{group_id}"
            )
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
        group_id = f"{message.chat.id}:{message.media_group_id}"
        _album_messages.setdefault(group_id, []).append(message)
        if group_id not in _album_tasks:
            _album_tasks[group_id] = asyncio.create_task(_flush_album(group_id), name=f"pixelpilot-album-{group_id}")
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
    prompt = (message.text or "").strip()
    if not prompt or prompt.startswith("/"):
        return
    if await _mode() == "generate":
        await _create_image(message, prompt)
    else:
        await _reply(message, prompt)
