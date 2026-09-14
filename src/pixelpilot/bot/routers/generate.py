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
    preset_keyboard,
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

PRESET_SUFFIXES: dict[str, str] = {
    "natural": "natural photorealistic photography, realistic materials and skin texture, natural proportions, believable lighting, subtle real-world imperfections",
    "portrait": "natural photorealistic portrait photography, realistic skin texture, expressive eyes, believable facial anatomy, soft optical depth of field, natural lighting",
    "full_body": "photorealistic full-body photography, complete person visible from head to feet, natural human anatomy and proportions, realistic hands and feet, believable posture",
    "fashion": "high-end editorial fashion photography, realistic fabric texture and drape, natural human anatomy, elegant composition, premium lighting, believable skin texture",
    "outdoor": "photorealistic outdoor photography, natural daylight, believable atmospheric depth, realistic textures, organic color response, subtle lens character",
    "product": "premium commercial product photography, realistic material texture, precise geometry, controlled studio lighting, natural reflections, clean composition",
}


def configure(orchestrator: Orchestrator) -> None:
    global _orchestrator
    _orchestrator = orchestrator


def orch() -> Orchestrator:
    if _orchestrator is None:
        raise RuntimeError("Generate router not configured")
    return _orchestrator


def apply_preset(prompt: str, preset: str) -> str:
    suffix = PRESET_SUFFIXES.get(preset, PRESET_SUFFIXES["natural"])
    return f"{prompt.strip()}, {suffix}" if prompt.strip() else suffix


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
    await callback.message.edit_text("🎨 اختر نوع الصورة:", reply_markup=preset_keyboard())


@router.callback_query(lambda q: q.data and q.data.startswith("generate:preset:"))
async def choose_preset(callback: CallbackQuery, state: FSMContext) -> None:
    preset = callback.data.rsplit(":", 1)[1]
    if preset not in PRESET_SUFFIXES:
        await safe_callback_answer(callback, "اختيار غير معروف", show_alert=True)
        return
    await state.update_data(preset=preset)
    await safe_callback_answer(callback)
    await callback.message.edit_text("📐 اختر أبعاد الصورة:", reply_markup=ratio_keyboard())


@router.callback_query(lambda q: q.data and q.data.startswith("generate:ratio:"))
async def choose_ratio(callback: CallbackQuery, state: FSMContext) -> None:
    ratio = callback.data.rsplit(":", 1)[1]
    if ratio not in RATIOS:
        await safe_callback_answer(callback, "مقاس غير معروف", show_alert=True)
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
        "✍️ أرسل وصف الصورة الآن.\n\n"
        "اكتب ما تريد بشكل طبيعي؛ PixelPilot سيضيف تحسينات خفيفة مناسبة للواقعية حسب النمط الذي اخترته."
    )


@router.message(GenerateStates.waiting_prompt, F.text)
async def receive_prompt(message: Message, state: FSMContext) -> None:
    raw_prompt = (message.text or "").strip()
    if not raw_prompt:
        await message.answer("أرسل وصفًا نصيًا للصورة.")
        return
    data = await state.get_data()
    preset = str(data.get("preset") or "natural")
    ratio = str(data.get("ratio") or "1x1")
    count = int(data.get("count") or 1)
    width, height = RATIOS[ratio]
    prepared_prompt = apply_preset(raw_prompt, preset)
    if len(prepared_prompt) > 4000:
        await message.answer("الوصف طويل جدًا. اختصره قليلًا (الحد بعد تحسينات PixelPilot هو 4000 حرف).")
        return
    spec = GenerationSpec(
        prompt=prepared_prompt,
        width=width,
        height=height,
        seed=secrets.randbits(63),
        steps=orch().settings.generation_default_steps,
        batch_size=count,
        preset=preset,
    )
    await state.clear()
    status_message = await message.answer(
        "⏳ <b>جاري التوليد...</b>\n"
        f"المقاس: {width}×{height}\n"
        f"العدد: {count}\n"
        f"Seed: <code>{spec.seed}</code>"
    )
    try:
        result = await orch().generate(spec)
        await status_message.edit_text("✅ اكتمل التوليد، جاري إرسال النتائج...")
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
        caption = (
            f"✨ Generation <code>#{result.generation_id}</code>\n"
            f"Seed: <code>{result.spec.seed}</code>\n"
            f"{result.spec.width}×{result.spec.height}"
        )
        keyboard = generation_image_keyboard(
            result.generation_id,
            index,
            show_rerun=index == 0,
        )
        try:
            await message.answer_photo(
                BufferedInputFile(content, filename=image_ref.filename),
                caption=caption,
                reply_markup=keyboard,
            )
        except Exception:
            await message.answer_document(
                BufferedInputFile(content, filename=image_ref.filename),
                caption=caption + "\n📄 أُرسلت كملف لأن معاينة Telegram لم تقبل الصورة.",
                reply_markup=keyboard,
            )
