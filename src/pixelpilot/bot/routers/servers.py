from __future__ import annotations

import logging
from html import escape

from aiogram import Router
from aiogram.types import CallbackQuery

from pixelpilot.bot.callbacks import safe_callback_answer
from pixelpilot.bot.keyboards import destroy_confirm_keyboard, main_menu, offer_confirm_keyboard, offers_keyboard
from pixelpilot.preflight import run_external_preflight, run_local_preflight
from pixelpilot.services.orchestrator import Orchestrator

router = Router(name="servers")
logger = logging.getLogger(__name__)
_orchestrator: Orchestrator | None = None


def configure(orchestrator: Orchestrator) -> None:
    global _orchestrator
    _orchestrator = orchestrator


def orch() -> Orchestrator:
    if _orchestrator is None:
        raise RuntimeError("Server router not configured")
    return _orchestrator


@router.callback_query(lambda q: q.data == "servers:preflight")
async def preflight(callback: CallbackQuery) -> None:
    await safe_callback_answer(callback)
    checks = run_local_preflight(orch().settings)
    if all(item.ok for item in checks):
        checks.extend(await run_external_preflight(orch().settings))

    if not all(item.ok for item in checks):
        logger.warning(
            "PixelPilot preflight failed: %s",
            [(item.name, item.detail) for item in checks if not item.ok],
        )
        await callback.message.edit_text(
            "❌ <b>يوجد خلل في الإعدادات</b>\n\nتأكد من إعدادات المشروع ثم أعد الفحص.",
            reply_markup=main_menu(),
        )
        return

    try:
        offers = await orch().offers()
    except Exception:
        logger.exception("Server availability check failed")
        await callback.message.edit_text(
            "❌ تعذر إكمال الفحص الآن. جرّب مرة أخرى بعد قليل.",
            reply_markup=main_menu(),
        )
        return

    await callback.message.edit_text(
        f"✅ <b>كل شيء جاهز</b>\n\nيوجد {len(offers)} عرض متاح حاليًا.",
        reply_markup=main_menu(),
    )


@router.callback_query(lambda q: q.data == "servers:search")
async def search(callback: CallbackQuery) -> None:
    await safe_callback_answer(callback, "جاري البحث...")
    await callback.message.edit_text("🔎 أبحث عن السيرفرات المتاحة...")
    try:
        offers = await orch().offers()
    except Exception:
        logger.exception("Server offer search failed")
        await callback.message.edit_text(
            "❌ تعذر البحث عن السيرفرات الآن. جرّب مرة أخرى.",
            reply_markup=main_menu(),
        )
        return
    if not offers:
        await callback.message.edit_text(
            "لا توجد عروض مناسبة حاليًا. جرّب التحديث بعد قليل.",
            reply_markup=main_menu(),
        )
        return
    await callback.message.edit_text(
        "🧾 <b>العروض المتاحة</b>\nاختر عرضًا لمراجعة السعر والمواصفات:",
        reply_markup=offers_keyboard(offers),
    )


@router.callback_query(lambda q: q.data and q.data.startswith("servers:offer:"))
async def offer_details(callback: CallbackQuery) -> None:
    offer_id = int(callback.data.rsplit(":", 1)[1])
    offer = await orch().cached_offer(offer_id)
    await safe_callback_answer(callback)
    if offer is None:
        await callback.message.edit_text(
            "العرض لم يعد موجودًا في آخر نتائج البحث.",
            reply_markup=main_menu(),
        )
        return

    lines = [
        "🖥 <b>تفاصيل العرض</b>",
        f"GPU: <b>{escape(offer.gpu_name)}</b>",
        f"VRAM: <b>{offer.gpu_ram_gb:.0f} GB</b>",
        f"السعر: <b>${offer.price_per_hour:.3f}/ساعة</b>",
        f"الموثوقية: <b>{'?' if offer.reliability is None else f'{offer.reliability * 100:.1f}%'} </b>",
    ]
    if offer.inet_down_mbps:
        lines.append(f"سرعة التنزيل: <b>{offer.inet_down_mbps:.0f} Mbps</b>")
    if offer.location:
        lines.append(f"الموقع: <b>{escape(offer.location)}</b>")
    lines.extend([
        "",
        "⚠️ يبدأ احتساب التكلفة عند الاستئجار. احذف السيرفر عند الانتهاء لإيقاف التكلفة.",
    ])
    await callback.message.edit_text("\n".join(lines), reply_markup=offer_confirm_keyboard(offer_id))


@router.callback_query(lambda q: q.data and q.data.startswith("servers:rent:"))
async def rent(callback: CallbackQuery) -> None:
    offer_id = int(callback.data.rsplit(":", 1)[1])
    await safe_callback_answer(callback, "بدء الاستئجار")
    await callback.message.edit_text("🚀 جاري إنشاء السيرفر...")

    async def progress(_text: str) -> None:
        try:
            await callback.message.edit_text(
                "⏳ <b>جاري تجهيز السيرفر...</b>\n\nقد يستغرق ذلك عدة دقائق."
            )
        except Exception:
            pass

    try:
        await orch().rent_and_prepare(offer_id, progress=progress)
    except Exception:
        logger.exception("Server rent/provision failed")
        await callback.message.edit_text(
            "❌ <b>تعذر تجهيز السيرفر</b>\n\n"
            "إذا ظهر لديك كسيرفر حالي، احذفه من زر «حذف السيرفر» لإيقاف التكلفة.",
            reply_markup=main_menu(),
        )
        return

    await callback.message.edit_text(
        "✅ <b>السيرفر جاهز</b>\n\nأرسل الآن نصًا أو صورة أو تسجيلًا صوتيًا.",
        reply_markup=main_menu(),
    )


@router.callback_query(lambda q: q.data == "servers:destroy_confirm")
async def destroy_confirm(callback: CallbackQuery) -> None:
    await safe_callback_answer(callback)
    await callback.message.edit_text(
        "⚠️ سيتم حذف السيرفر نهائيًا وإيقافه.\nهل أنت متأكد؟",
        reply_markup=destroy_confirm_keyboard(),
    )


@router.callback_query(lambda q: q.data == "servers:destroy")
async def destroy(callback: CallbackQuery) -> None:
    await safe_callback_answer(callback, "جاري الحذف...")
    try:
        destroyed = await orch().destroy_current()
    except Exception:
        logger.exception("Server destroy failed")
        await callback.message.edit_text(
            "❌ تعذر حذف السيرفر الآن. جرّب مرة أخرى.",
            reply_markup=main_menu(),
        )
        return
    text = "🗑 تم حذف السيرفر نهائيًا." if destroyed else "لا يوجد سيرفر حالي."
    await callback.message.edit_text(text, reply_markup=main_menu())


@router.callback_query(lambda q: q.data == "servers:stop")
async def stop(callback: CallbackQuery) -> None:
    await safe_callback_answer(callback, "جاري الإيقاف...")
    try:
        stopped = await orch().stop_current()
    except Exception:
        logger.exception("Server stop failed")
        await callback.message.edit_text(
            "❌ تعذر إيقاف السيرفر الآن.",
            reply_markup=main_menu(),
        )
        return
    text = (
        "⏹ تم إيقاف السيرفر. قد تستمر رسوم التخزين أثناء الإيقاف."
        if stopped
        else "لا يوجد سيرفر حالي."
    )
    await callback.message.edit_text(text, reply_markup=main_menu())


@router.callback_query(lambda q: q.data == "servers:start")
async def start_instance(callback: CallbackQuery) -> None:
    await safe_callback_answer(callback, "جاري التشغيل...")
    await callback.message.edit_text("▶️ جاري تشغيل السيرفر...")

    async def progress(_text: str) -> None:
        try:
            await callback.message.edit_text("⏳ <b>جاري تشغيل السيرفر...</b>")
        except Exception:
            pass

    try:
        started = await orch().start_current(progress=progress)
    except Exception:
        logger.exception("Server start failed")
        await callback.message.edit_text(
            "❌ تعذر تشغيل السيرفر الآن.",
            reply_markup=main_menu(),
        )
        return
    text = "✅ السيرفر جاهز." if started else "لا يوجد سيرفر حالي."
    await callback.message.edit_text(text, reply_markup=main_menu())


def _status_label(state: dict) -> str:
    phase = str(state.get("phase") or "none")
    labels = {
        "none": "لا يوجد سيرفر",
        "renting": "⏳ جاري الاستئجار",
        "booting": "⏳ جاري التشغيل",
        "provisioning": "⏳ جاري التجهيز",
        "ready": "✅ جاهز",
        "stopping": "⏳ جاري الإيقاف",
        "stopped": "⏹ متوقف",
        "destroying": "⏳ جاري الحذف",
        "error": "⚠️ يحتاج مراجعة",
    }
    label = labels.get(phase, "ℹ️ قيد المعالجة")
    if phase == "ready" and state.get("inference_ready") is False:
        return "⚠️ غير جاهز"
    return label


@router.callback_query(lambda q: q.data == "servers:status")
async def status(callback: CallbackQuery) -> None:
    await safe_callback_answer(callback)
    try:
        state = await orch().current_state(probe_inference=True)
    except Exception:
        logger.exception("Server status check failed")
        await callback.message.edit_text(
            "❌ تعذر قراءة حالة السيرفر الآن.",
            reply_markup=main_menu(),
        )
        return

    if not state.get("instance_id"):
        await callback.message.edit_text(
            "📊 <b>حالة السيرفر</b>\n\nلا يوجد سيرفر حالي.",
            reply_markup=main_menu(),
        )
        return

    lines = [
        "📊 <b>حالة السيرفر</b>",
        "",
        _status_label(state),
    ]
    offer = state.get("offer")
    if isinstance(offer, dict) and offer.get("price_per_hour") is not None:
        lines.append(f"السعر: <b>${float(offer['price_per_hour']):.3f}/ساعة</b>")
    await callback.message.edit_text("\n".join(lines), reply_markup=main_menu())
