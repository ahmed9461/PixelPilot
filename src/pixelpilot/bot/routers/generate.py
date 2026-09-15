from __future__ import annotations

import secrets
from html import escape
from typing import Any

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from pixelpilot.bot.callbacks import safe_callback_answer
from pixelpilot.bot.keyboards import (
    count_keyboard,
    generation_image_keyboard,
    main_menu,
    quality_profile_keyboard,
    ratio_keyboard,
)
from pixelpilot.domain import GenerationResult, GenerationSpec, InstancePhase
from pixelpilot.services.orchestrator import Orchestrator

router = Router(name="generate")
_orchestrator: Orchestrator | None = None


class GenerateStates(StatesGroup):
    waiting_prompt = State()


RATIOS: dict[str, tuple[int, int]] = {
    "1x1": (1024, 1024),
    "4x5": (896, 1120),
    "3x2": (1216, 832),
    "16x9": (1344, 768),
    "9x16": (768, 1344),
}

QUALITY_STEPS: dict[str, int] = {
    "flux2_balanced": 28,
    "flux2_quality": 50,
}

QUALITY_LABELS: dict[str, str] = {
    "flux2_balanced": "FLUX.2 Balanced",
    "flux2_quality": "FLUX.2 Quality",
    # Historical rows can still be re-run after the migration.
    "official": "FLUX.2 Legacy",
    "krea_quality": "FLUX.2 Legacy",
}


def configure(orchestrator: Orchestrator) -> None:
    global _orchestrator
    _orchestrator = orchestrator


def orch() -> Orchestrator:
    if _orchestrator is None:
        raise RuntimeError("Generate router not configured")
    return _orchestrator


@router.callback_query(lambda q: q.data == "generate:start")
async def generate_start(callback: CallbackQuery, state: FSMContext) -> None:
    await safe_callback_answer(callback)
    phase = await orch().db.get("instance.phase", InstancePhase.NONE.value)
    if phase != InstancePhase.READY.value:
        await callback.message.edit_text(
            "🎨 لا أقدر أبدأ التوليد الآن لأن السيرفر غير جاهز.\n"
            f"الحالة الحالية: <b>{escape(str(phase))}</b>\n\n"
            "استأجر سيرفر أولًا أو شغّل السيرفر الحالي.",
            reply_markup=main_menu(),
        )
        return
    await state.clear()
    await callback.message.edit_text(
        "🎨 <b>اختر وضع FLUX.2</b>\n\n"
        "⚡ <b>Balanced</b>: 28 خطوة + guidance 4.0 — أسرع للاستخدام اليومي\n"
        "✨ <b>Quality</b>: 50 خطوة + guidance 4.0 — أقصى جودة للاختبار والنتيجة النهائية\n\n"
        "🔒 <b>مهم:</b> PixelPilot سيرسل البرومبت الذي تكتبه كما هو حرفيًا، بدون إضافة أو تحسين أو ترجمة.",
        reply_markup=quality_profile_keyboard(),
    )


@router.callback_query(lambda q: q.data and q.data.startswith("generate:quality:"))
async def choose_quality(callback: CallbackQuery, state: FSMContext) -> None:
    quality_profile = callback.data.rsplit(":", 1)[1]
    if quality_profile not in QUALITY_STEPS:
        await safe_callback_answer(callback, "وضع جودة غير معروف", show_alert=True)
        return
    await state.update_data(quality_profile=quality_profile)
    await safe_callback_answer(callback)
    await callback.message.edit_text(
        f"✅ الوضع: <b>{QUALITY_LABELS[quality_profile]}</b>\n\n📐 اختر أبعاد الصورة:",
        reply_markup=ratio_keyboard(),
    )


@router.callback_query(lambda q: q.data and q.data.startswith("generate:preset:"))
async def legacy_preset(callback: CallbackQuery, state: FSMContext) -> None:
    """Handle buttons left in old Telegram messages without modifying prompts."""
    await state.clear()
    await safe_callback_answer(callback, "تم إلغاء أنماط تعديل البرومبت")
    await callback.message.edit_text(
        "تم إلغاء أنماط تعديل البرومبت. اختر وضع FLUX.2:",
        reply_markup=quality_profile_keyboard(),
    )


@router.callback_query(lambda q: q.data and q.data.startswith("generate:ratio:"))
async def choose_ratio(callback: CallbackQuery, state: FSMContext) -> None:
    ratio = callback.data.rsplit(":", 1)[1]
    if ratio not in RATIOS:
        await safe_callback_answer(callback, "مقاس غير معروف", show_alert=True)
        return
    data = await state.get_data()
    if str(data.get("quality_profile") or "") not in QUALITY_STEPS:
        await safe_callback_answer(callback, "اختر وضع التوليد أولًا", show_alert=True)
        return
    await state.update_data(ratio=ratio)
    await safe_callback_answer(callback)
    await callback.message.edit_text(
        "🖼 كم صورة تريد في هذه الدفعة؟",
        reply_markup=count_keyboard(orch().settings.generation_max_batch),
    )


@router.callback_query(lambda q: q.data and q.data.startswith("generate:count:"))
async def choose_count(callback: CallbackQuery, state: FSMContext) -> None:
    count = int(callback.data.rsplit(":", 1)[1])
    if count < 1 or count > orch().settings.generation_max_batch:
        await safe_callback_answer(callback, "عدد غير مسموح", show_alert=True)
        return
    await state.update_data(count=count)
    await state.set_state(GenerateStates.waiting_prompt)
    await safe_callback_answer(callback)
    await callback.message.edit_text(
        "✍️ أرسل البرومبت الآن.\n\n"
        "🔒 سيتم تمريره إلى FLUX.2 <b>كما كتبته بالضبط</b>، بدون suffix أو تحسين تلقائي أو ترجمة."
    )


@router.message(GenerateStates.waiting_prompt, F.text)
async def receive_prompt(message: Message, state: FSMContext) -> None:
    # Preserve the user's prompt exactly. strip() is used only to reject a
    # whitespace-only message; the model receives raw_prompt unchanged.
    raw_prompt = message.text or ""
    if not raw_prompt.strip():
        await message.answer("أرسل وصفًا نصيًا للصورة.")
        return
    if len(raw_prompt) > 4000:
        await message.answer("البرومبت طويل جدًا. الحد هو 4000 حرف.")
        return

    data = await state.get_data()
    quality_profile = str(data.get("quality_profile") or "flux2_balanced")
    ratio = str(data.get("ratio") or "1x1")
    count = int(data.get("count") or 1)
    if quality_profile not in QUALITY_STEPS:
        quality_profile = "flux2_balanced"
    width, height = RATIOS[ratio]

    spec = GenerationSpec(
        prompt=raw_prompt,
        width=width,
        height=height,
        seed=secrets.randbits(63),
        steps=QUALITY_STEPS[quality_profile],
        batch_size=count,
        preset="raw",
        quality_profile=quality_profile,
    )
    await state.clear()
    status_message = await message.answer(
        "⏳ <b>جاري التوليد بـ FLUX.2...</b>\n"
        f"الوضع: {QUALITY_LABELS[quality_profile]}\n"
        f"المقاس: {width}×{height}\n"
        f"الخطوات: {spec.steps}\n"
        f"العدد: {count}\n"
        f"Seed: <code>{spec.seed}</code>"
    )
    try:
        result = await orch().generate(spec)
        await status_message.edit_text("✅ اكتمل التوليد، جاري إرسال PNG الأصلي بدون ضغط Telegram...")
        await _deliver_result(message, result)
        await status_message.delete()
    except Exception as exc:
        await status_message.edit_text(
            f"❌ فشل التوليد:\n<code>{escape(str(exc))}</code>",
            reply_markup=main_menu(),
        )


@router.callback_query(lambda q: q.data == "generate:cancel")
async def cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await safe_callback_answer(callback, "تم الإلغاء")
    await callback.message.edit_text("تم إلغاء إنشاء الصورة.", reply_markup=main_menu())


@router.callback_query(lambda q: q.data and q.data.startswith("generate:original:"))
async def original(callback: CallbackQuery) -> None:
    _, _, generation_id, image_index = callback.data.split(":")
    await safe_callback_answer(callback, "جاري إرسال الأصل...")
    try:
        content, ref = await orch().download_generation_image(int(generation_id), int(image_index))
    except Exception as exc:
        await callback.message.answer(f"❌ تعذر جلب الأصل: <code>{escape(str(exc))}</code>")
        return
    await callback.message.answer_document(
        BufferedInputFile(content, filename=ref.filename),
        caption=f"📄 الأصل — Generation #{generation_id}",
    )


@router.callback_query(lambda q: q.data and q.data.startswith("generate:rerun_same:"))
async def rerun_same(callback: CallbackQuery) -> None:
    generation_id = int(callback.data.rsplit(":", 1)[1])
    await safe_callback_answer(callback, "إعادة بنفس Seed")
    progress = await callback.message.answer("⏳ إعادة التوليد بنفس Seed...")
    try:
        result = await orch().regenerate(generation_id, same_seed=True)
        await _deliver_result(callback.message, result)
        await progress.delete()
    except Exception as exc:
        await progress.edit_text(f"❌ فشل التوليد: <code>{escape(str(exc))}</code>")


@router.callback_query(lambda q: q.data and q.data.startswith("generate:rerun_new:"))
async def rerun_new(callback: CallbackQuery) -> None:
    generation_id = int(callback.data.rsplit(":", 1)[1])
    await safe_callback_answer(callback, "Seed جديد")
    progress = await callback.message.answer("⏳ إعادة التوليد بـ Seed جديد...")
    try:
        result = await orch().regenerate(generation_id, same_seed=False)
        await _deliver_result(callback.message, result)
        await progress.delete()
    except Exception as exc:
        await progress.edit_text(f"❌ فشل التوليد: <code>{escape(str(exc))}</code>")


async def _deliver_result(message: Message, result: GenerationResult) -> None:
    for index, image_ref in enumerate(result.images):
        content, _ = await orch().download_generation_image(result.generation_id, index)
        quality_label = QUALITY_LABELS.get(result.spec.quality_profile, result.spec.quality_profile)
        caption = (
            f"✨ Generation <code>#{result.generation_id}</code>\n"
            f"Model: <b>FLUX.2 Dev</b>\n"
            f"Mode: <b>{escape(quality_label)}</b>\n"
            f"Seed: <code>{result.spec.seed}</code>\n"
            f"{result.spec.width}×{result.spec.height}\n"
            "📄 PNG الأصلي — بدون ضغط Telegram"
        )
        keyboard = generation_image_keyboard(
            result.generation_id,
            index,
            show_rerun=index == 0,
        )
        await message.answer_document(
            BufferedInputFile(content, filename=image_ref.filename),
            caption=caption,
            reply_markup=keyboard,
        )
