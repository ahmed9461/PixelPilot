from __future__ import annotations

from aiogram import Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from pixelpilot.bot.callbacks import safe_callback_answer, safe_edit_text
from pixelpilot.services.image_settings import (
    ASPECT_RATIOS,
    STEP_CHOICES,
    get_state,
    reset,
    set_aspect_ratio,
    set_quality,
    set_steps,
)
from pixelpilot.services.orchestrator import Orchestrator


router = Router(name="image-settings")
_orchestrator: Orchestrator | None = None


def configure(orchestrator: Orchestrator) -> None:
    global _orchestrator
    _orchestrator = orchestrator


def orch() -> Orchestrator:
    if _orchestrator is None:
        raise RuntimeError("Image settings router not configured")
    return _orchestrator


def _keyboard(aspect: str, quality: str, steps: int) -> InlineKeyboardMarkup:
    ratio_rows: list[list[InlineKeyboardButton]] = []
    ratios = list(ASPECT_RATIOS)
    for start in range(0, len(ratios), 3):
        ratio_rows.append(
            [
                InlineKeyboardButton(
                    text=("✓ " if item == aspect else "") + item,
                    callback_data=f"imagesettings:ratio:{item}",
                    style="success" if item == aspect else None,
                )
                for item in ratios[start : start + 3]
            ]
        )

    quality_row = [
        InlineKeyboardButton(
            text=("✓ " if quality == "standard" else "") + "⚡ قياسي",
            callback_data="imagesettings:quality:standard",
            style="success" if quality == "standard" else None,
        ),
        InlineKeyboardButton(
            text=("✓ " if quality == "high" else "") + "✨ 2K",
            callback_data="imagesettings:quality:high",
            style="success" if quality == "high" else None,
        ),
    ]

    steps_row = [
        InlineKeyboardButton(
            text=("✓ " if value == steps else "") + str(value),
            callback_data=f"imagesettings:steps:{value}",
            style="success" if value == steps else None,
        )
        for value in STEP_CHOICES
    ]

    return InlineKeyboardMarkup(
        inline_keyboard=[
            quality_row,
            *ratio_rows,
            steps_row,
            [InlineKeyboardButton(text="♻️ الافتراضي", callback_data="imagesettings:reset")],
            [InlineKeyboardButton(text="⬅️ الرئيسية", callback_data="home")],
        ]
    )


async def _render(callback: CallbackQuery) -> None:
    state = await get_state(orch().db)
    width, height = state.size
    quality_label = "قياسي" if state.quality == "standard" else "2K"
    await safe_edit_text(
        callback.message,
        "⚙️ <b>إعدادات الصور</b>\n\n"
        f"الجودة: <b>{quality_label}</b>\n"
        f"الأبعاد: <b>{state.aspect_ratio} — {width}×{height}</b>\n"
        f"خطوات التوليد: <b>{state.steps}</b>\n\n"
        "وضع «قياسي» أخف وأسرع ومناسب لسيرفرات 24GB. "
        "وضع «2K» يعطي دقة أعلى ويُفضّل له GPU بذاكرة 48GB أو أكثر.\n\n"
        "لا يوجد برومت مخفي ولا شخصية أو نبرة مفروضة؛ وصفك يُرسل كما كتبته.",
        reply_markup=_keyboard(state.aspect_ratio, state.quality, state.steps),
    )


@router.callback_query(lambda q: q.data == "imagesettings:open")
async def open_settings(callback: CallbackQuery) -> None:
    await safe_callback_answer(callback)
    await _render(callback)


@router.callback_query(lambda q: q.data and q.data.startswith("imagesettings:ratio:"))
async def choose_ratio(callback: CallbackQuery) -> None:
    value = callback.data.split(":", 2)[2]
    try:
        await set_aspect_ratio(orch().db, value)
    except ValueError:
        await safe_callback_answer(callback, "خيار غير صالح", show_alert=True)
        return
    await safe_callback_answer(callback, "تم")
    await _render(callback)


@router.callback_query(lambda q: q.data and q.data.startswith("imagesettings:quality:"))
async def choose_quality(callback: CallbackQuery) -> None:
    value = callback.data.rsplit(":", 1)[1]
    try:
        await set_quality(orch().db, value)
    except ValueError:
        await safe_callback_answer(callback, "خيار غير صالح", show_alert=True)
        return
    await safe_callback_answer(callback, "تم")
    await _render(callback)


@router.callback_query(lambda q: q.data and q.data.startswith("imagesettings:steps:"))
async def choose_steps(callback: CallbackQuery) -> None:
    try:
        value = int(callback.data.rsplit(":", 1)[1])
        await set_steps(orch().db, value)
    except (TypeError, ValueError):
        await safe_callback_answer(callback, "خيار غير صالح", show_alert=True)
        return
    await safe_callback_answer(callback, "تم")
    await _render(callback)


@router.callback_query(lambda q: q.data == "imagesettings:reset")
async def reset_settings(callback: CallbackQuery) -> None:
    await reset(orch().db)
    await safe_callback_answer(callback, "تمت الاستعادة")
    await _render(callback)
