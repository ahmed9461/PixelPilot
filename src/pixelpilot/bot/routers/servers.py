from __future__ import annotations

import asyncio
import logging
from html import escape
from typing import Any

from aiogram import Router
from aiogram.types import CallbackQuery, Message

from pixelpilot.bot.callbacks import safe_callback_answer
from pixelpilot.bot.keyboards import destroy_confirm_keyboard, main_menu, offer_confirm_keyboard, offers_keyboard
from pixelpilot.preflight import run_external_preflight, run_local_preflight
from pixelpilot.services.orchestrator import Orchestrator

router = Router(name="servers")
logger = logging.getLogger(__name__)
_orchestrator: Orchestrator | None = None
_lifecycle_task: asyncio.Task[None] | None = None


def configure(orchestrator: Orchestrator) -> None:
    global _orchestrator
    _orchestrator = orchestrator


def orch() -> Orchestrator:
    if _orchestrator is None:
        raise RuntimeError("Server router not configured")
    return _orchestrator


def _lifecycle_busy() -> bool:
    return _lifecycle_task is not None and not _lifecycle_task.done()


def _track_lifecycle(coro: Any, *, name: str) -> None:
    global _lifecycle_task
    task = asyncio.create_task(coro, name=name)
    _lifecycle_task = task

    def _done(completed: asyncio.Task[None]) -> None:
        global _lifecycle_task
        if _lifecycle_task is completed:
            _lifecycle_task = None
        if completed.cancelled():
            return
        try:
            exc = completed.exception()
        except asyncio.CancelledError:
            return
        if exc is not None:
            logger.exception(
                "Background server lifecycle task failed",
                exc_info=(type(exc), exc, exc.__traceback__),
            )

    task.add_done_callback(_done)


async def _cancel_lifecycle_if_running() -> None:
    global _lifecycle_task
    task = _lifecycle_task
    if task is None or task.done():
        return
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    if _lifecycle_task is task:
        _lifecycle_task = None


async def _prepare_manual_control(callback: CallbackQuery) -> bool:
    instance_id = await orch().db.get("instance.id")
    phase = str(
        await orch().db.get("instance.phase", "none")
        or "none"
    )
    if not instance_id and phase == "renting":
        await callback.message.edit_text(
            "⏳ <b>Vast ما زال ينشئ السيرفر</b>\n\n"
            "لم يصل رقم الـInstance بعد، لذلك لن ألغي الطلب بطريقة قد تترك "
            "سيرفرًا مدفوعًا بدون تتبع. انتظر ظهور رقم السيرفر ثم استخدم "
            "الإيقاف أو الحذف.",
            reply_markup=main_menu(),
        )
        return False

    if instance_id:
        await _cancel_lifecycle_if_running()
    return True


def _offer_signature(item: Any) -> tuple[Any, ...]:
    if isinstance(item, dict):
        return (
            int(item.get("offer_id") or 0),
            round(float(item.get("price_per_hour") or 0.0), 6),
            round(float(item.get("reliability") or 0.0), 6),
            round(float(item.get("inet_down_mbps") or 0.0), 3),
            str(item.get("gpu_name") or ""),
        )
    return (
        int(item.offer_id),
        round(float(item.price_per_hour), 6),
        round(float(item.reliability or 0.0), 6),
        round(float(item.inet_down_mbps or 0.0), 3),
        str(item.gpu_name),
    )


def _refresh_note(
    previous: list[Any],
    current: list[Any],
    refresh_no: int | None = None,
) -> str:
    prefix = f"🔄 تحديث السوق #{refresh_no}" if refresh_no else "🔄 تم تحديث السوق الآن"
    if not previous:
        return f"{prefix} — تم فحص السوق الآن."

    old = [_offer_signature(item) for item in previous]
    new = [_offer_signature(item) for item in current]
    if old == new:
        return f"{prefix} — تم فحص السوق الآن، ونفس النتائج ما زالت متاحة."

    old_ids = {item[0] for item in old}
    new_ids = {item[0] for item in new}
    added = len(new_ids - old_ids)
    removed = len(old_ids - new_ids)
    if added or removed:
        return f"{prefix} — {added} عرض جديد و{removed} عرض اختفى."
    return f"{prefix} — تغيّرت الأسعار أو ترتيب العروض."


def _format_duration(seconds: float) -> str:
    total = max(0, int(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def _billing_lines(billing: Any, *, final: bool = False) -> list[str]:
    if not isinstance(billing, dict):
        return []
    active_seconds = float(billing.get("active_seconds") or 0.0)
    cost = float(billing.get("estimated_cost_usd") or 0.0)
    label = "التكلفة النهائية المقدرة" if final else "التكلفة حتى الآن"
    return [
        f"⏱ وقت التشغيل المحتسب: <b>{_format_duration(active_seconds)}</b>",
        f"💵 {label}: <b>${cost:.4f}</b>",
    ]


@router.callback_query(lambda q: q.data == "servers:preflight")
async def preflight(callback: CallbackQuery) -> None:
    await safe_callback_answer(callback, "جاري الفحص...")
    await callback.message.edit_text(
        "🧪 <b>جاري فحص الجاهزية...</b>\n\n"
        "أتحقق من إعدادات المشروع والوصول إلى Git وQwen.",
        reply_markup=main_menu(),
    )

    checks = run_local_preflight(orch().settings)
    if all(item.ok for item in checks):
        checks.extend(await run_external_preflight(orch().settings))

    if not all(item.ok for item in checks):
        logger.warning(
            "PixelPilot preflight failed: %s",
            [(item.name, item.detail) for item in checks if not item.ok],
        )
        failed = [
            f"❌ {escape(item.name)}: {escape(item.detail)}"
            for item in checks
            if not item.ok
        ]
        await callback.message.edit_text(
            "❌ <b>يوجد خلل في الجاهزية</b>\n\n"
            + "\n".join(failed),
            reply_markup=main_menu(),
        )
        return

    await callback.message.edit_text(
        "✅ <b>فحص الجاهزية ناجح</b>\n\n"
        "الإعدادات ومصدر المشروع والوصول إلى Qwen سليمة. "
        "البحث عن عروض Vast أصبح منفصلًا حتى يبقى هذا الفحص سريعًا.",
        reply_markup=main_menu(),
    )


async def _search_offers(callback: CallbackQuery, *, preferred_only: bool) -> None:
    mode = "preferred" if preferred_only else "all"
    await safe_callback_answer(callback, "جاري التحديث...")
    loading = (
        "🔥 أبحث عن سيرفرات 48GB+ المتاحة..."
        if preferred_only
        else "🔎 أبحث عن أفضل السيرفرات المتاحة..."
    )
    await callback.message.edit_text(loading)

    previous_mode = str(await orch().db.get("offers.search_mode", "all") or "all")
    previous = await orch().db.get("offers.last", [])
    if previous_mode != mode or not isinstance(previous, list):
        previous = []

    try:
        offers = await orch().offers(preferred_only=preferred_only)
    except Exception:
        logger.exception("Server offer search failed")
        await callback.message.edit_text(
            "❌ تعذر البحث عن السيرفرات الآن. جرّب مرة أخرى.",
            reply_markup=main_menu(),
        )
        return

    refresh_no = int(await orch().db.get("offers.refresh_serial", 0) or 0) + 1
    await orch().db.set("offers.refresh_serial", refresh_no)

    candidate_count = int(await orch().db.get("offers.candidate_count", 0) or 0)
    preferred_count = int(
        await orch().db.get("offers.preferred_candidate_count", 0) or 0
    )

    if not offers:
        scope = (
            "لا توجد حاليًا عروض 48GB+ مطابقة للفلاتر وسقف السعر."
            if preferred_only
            else "لا توجد عروض مناسبة حاليًا ضمن الفلاتر وسقف السعر المحدد."
        )
        await callback.message.edit_text(
            f"🔄 <b>تحديث السوق #{refresh_no}</b>\n\n{scope}",
            reply_markup=offers_keyboard([], preferred_only=preferred_only),
        )
        return

    note = _refresh_note(previous, offers, refresh_no)
    await orch().db.set("offers.last_refresh_note", note)

    if preferred_only:
        title = "🔥 <b>عروض 48GB+ المتاحة</b>"
        discovery = f"المرشحون المطابقون: <b>{candidate_count}</b>"
    else:
        title = "🧾 <b>أفضل العروض المتاحة</b>"
        discovery = (
            f"المرشحون المطابقون: <b>{candidate_count}</b> "
            f"— منها 48GB+: <b>{preferred_count}</b>"
        )

    await callback.message.edit_text(
        f"{title}\n{note}\n"
        f"{discovery}\n"
        f"المعروض لك الآن: <b>{len(offers)}</b>\n\n"
        "اختر عرضًا لمراجعة السعر والمواصفات:",
        reply_markup=offers_keyboard(offers, preferred_only=preferred_only),
    )


@router.callback_query(lambda q: q.data == "servers:search")
async def search(callback: CallbackQuery) -> None:
    await _search_offers(callback, preferred_only=False)


@router.callback_query(lambda q: q.data == "servers:search48")
async def search_preferred(callback: CallbackQuery) -> None:
    await _search_offers(callback, preferred_only=True)


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
    profile = (
        "🚀 مفضّل — مناسب لوضع GPU الكامل و2K"
        if offer.gpu_ram_gb >= orch().settings.vast_preferred_gpu_ram_gb
        else "💡 اقتصادي — يعمل بوضع توفير الذاكرة، ويفضّل معه القياسي"
    )
    lines.append(f"ملف التشغيل: <b>{profile}</b>")
    if offer.inet_down_mbps:
        lines.append(f"سرعة التنزيل: <b>{offer.inet_down_mbps:.0f} Mbps</b>")
    if offer.location:
        lines.append(f"الموقع: <b>{escape(offer.location)}</b>")
    lines.extend([
        "",
        "⚠️ يبدأ عداد التكلفة عند الاستئجار، ويُحسب بالثانية حتى الإيقاف أو الحذف.",
    ])
    preferred_only = (
        str(await orch().db.get("offers.search_mode", "all") or "all")
        == "preferred"
    )
    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=offer_confirm_keyboard(
            offer_id,
            preferred_only=preferred_only,
        ),
    )


async def _rent_and_prepare_background(
    offer_id: int,
    status_message: Message,
) -> None:
    async def progress(_text: str) -> None:
        try:
            state = await orch().current_state(probe_inference=False)
            billing = state.get("billing") if isinstance(state, dict) else None
            lines = [
                "⏳ <b>جاري تجهيز محرك الصور...</b>",
                "",
                "التجهيز يعمل في الخلفية؛ تستطيع استخدام أزرار الحالة والحذف أثناء ذلك.",
            ]
            lines.extend(_billing_lines(billing))
            await status_message.edit_text("\n".join(lines))
        except Exception:
            pass

    try:
        await orch().rent_and_prepare(offer_id, progress=progress)
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("Server rent/provision failed")
        current_id = await orch().db.get("instance.id")
        if not current_id:
            text = "ℹ️ انتهت مهمة التجهيز لأن السيرفر لم يعد موجودًا."
        else:
            text = (
                "❌ <b>تعذر تجهيز السيرفر</b>\n\n"
                "يمكنك فحص الحالة أو حذف السيرفر لإيقاف التكلفة."
            )
        try:
            await status_message.edit_text(text, reply_markup=main_menu())
        except Exception:
            pass
        return

    try:
        state = await orch().current_state(probe_inference=False)
        lines = [
            "✅ <b>السيرفر جاهز</b>",
            "",
            "أرسل وصفًا لإنشاء صورة، أو صورة مع تعليمات لتعديلها.",
        ]
        lines.extend(_billing_lines(state.get("billing")))
        await status_message.edit_text("\n".join(lines), reply_markup=main_menu())
    except Exception:
        logger.exception("Could not render ready status")


@router.callback_query(lambda q: q.data and q.data.startswith("servers:rent:"))
async def rent(callback: CallbackQuery) -> None:
    if _lifecycle_busy():
        await safe_callback_answer(
            callback,
            "يوجد تجهيز أو تشغيل جارٍ بالفعل",
            show_alert=True,
        )
        return

    offer_id = int(callback.data.rsplit(":", 1)[1])
    await safe_callback_answer(callback, "بدأ التجهيز بالخلفية")
    await callback.message.edit_text(
        "🚀 <b>بدأ استئجار وتجهيز السيرفر</b>\n\n"
        "يمكنك الآن استخدام «حالة السيرفر» و«فحص الجاهزية» بدون انتظار انتهاء التجهيز.",
        reply_markup=main_menu(),
    )
    status_message = await callback.message.answer(
        "⏳ <b>جاري بدء التجهيز...</b>"
    )
    _track_lifecycle(
        _rent_and_prepare_background(offer_id, status_message),
        name="pixelpilot-rent-and-prepare",
    )


@router.callback_query(lambda q: q.data == "servers:destroy_confirm")
async def destroy_confirm(callback: CallbackQuery) -> None:
    await safe_callback_answer(callback)
    try:
        state = await orch().current_state(probe_inference=False)
        billing = state.get("billing") if isinstance(state, dict) else None
    except Exception:
        billing = None
    lines = ["⚠️ سيتم حذف السيرفر نهائيًا وإيقافه."]
    lines.extend(_billing_lines(billing))
    lines.extend(["", "هل أنت متأكد؟"])
    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=destroy_confirm_keyboard(),
    )


@router.callback_query(lambda q: q.data == "servers:destroy")
async def destroy(callback: CallbackQuery) -> None:
    await safe_callback_answer(callback, "جاري الحذف...")
    if not await _prepare_manual_control(callback):
        return
    try:
        destroyed = await orch().destroy_current()
    except Exception:
        logger.exception("Server destroy failed")
        await callback.message.edit_text(
            "❌ تعذر حذف السيرفر الآن. جرّب مرة أخرى.",
            reply_markup=main_menu(),
        )
        return
    if not destroyed:
        await callback.message.edit_text("لا يوجد سيرفر حالي.", reply_markup=main_menu())
        return
    billing = await orch().last_billing_snapshot()
    lines = ["🗑 تم حذف السيرفر نهائيًا."]
    lines.extend(_billing_lines(billing, final=True))
    if billing:
        lines.append("<i>قد توجد رسوم تخزين أو بيانات منفصلة عن عداد التشغيل.</i>")
    await callback.message.edit_text("\n".join(lines), reply_markup=main_menu())


@router.callback_query(lambda q: q.data == "servers:stop")
async def stop(callback: CallbackQuery) -> None:
    await safe_callback_answer(callback, "جاري الإيقاف...")
    if not await _prepare_manual_control(callback):
        return
    try:
        stopped = await orch().stop_current()
    except Exception:
        logger.exception("Server stop failed")
        await callback.message.edit_text(
            "❌ تعذر إيقاف السيرفر الآن.",
            reply_markup=main_menu(),
        )
        return
    if not stopped:
        await callback.message.edit_text("لا يوجد سيرفر حالي.", reply_markup=main_menu())
        return
    state = await orch().current_state(probe_inference=False)
    lines = ["⏹ تم إيقاف السيرفر. قد تستمر رسوم التخزين أثناء الإيقاف."]
    lines.extend(_billing_lines(state.get("billing")))
    await callback.message.edit_text("\n".join(lines), reply_markup=main_menu())


async def _start_background(status_message: Message) -> None:
    async def progress(_text: str) -> None:
        try:
            state = await orch().current_state(probe_inference=False)
            lines = [
                "⏳ <b>جاري تشغيل السيرفر...</b>",
                "",
                "التشغيل مستمر في الخلفية.",
            ]
            lines.extend(_billing_lines(state.get("billing")))
            await status_message.edit_text("\n".join(lines))
        except Exception:
            pass

    try:
        started = await orch().start_current(progress=progress)
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("Server start failed")
        try:
            await status_message.edit_text(
                "❌ تعذر تشغيل السيرفر الآن.",
                reply_markup=main_menu(),
            )
        except Exception:
            pass
        return

    if not started:
        await status_message.edit_text(
            "لا يوجد سيرفر حالي.",
            reply_markup=main_menu(),
        )
        return

    state = await orch().current_state(probe_inference=False)
    lines = ["✅ السيرفر جاهز."]
    lines.extend(_billing_lines(state.get("billing")))
    await status_message.edit_text("\n".join(lines), reply_markup=main_menu())


@router.callback_query(lambda q: q.data == "servers:start")
async def start_instance(callback: CallbackQuery) -> None:
    if _lifecycle_busy():
        await safe_callback_answer(
            callback,
            "يوجد تجهيز أو تشغيل جارٍ بالفعل",
            show_alert=True,
        )
        return

    await safe_callback_answer(callback, "بدأ التشغيل بالخلفية")
    await callback.message.edit_text(
        "▶️ <b>بدأ تشغيل السيرفر</b>\n\n"
        "يمكنك متابعة الحالة أثناء التشغيل.",
        reply_markup=main_menu(),
    )
    status_message = await callback.message.answer("⏳ جاري تشغيل السيرفر...")
    _track_lifecycle(
        _start_background(status_message),
        name="pixelpilot-start-instance",
    )


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
    await safe_callback_answer(callback, "جاري قراءة الحالة...")
    await callback.message.edit_text(
        "📊 <b>جاري قراءة حالة السيرفر...</b>",
        reply_markup=main_menu(),
    )
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
        phase = str(state.get("phase") or "none")
        if phase == "none":
            body = "لا يوجد سيرفر حالي."
        else:
            body = _status_label(state)
        await callback.message.edit_text(
            f"📊 <b>حالة السيرفر</b>\n\n{body}",
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
    lines.extend(_billing_lines(state.get("billing")))
    if state.get("billing"):
        lines.append("<i>العداد مباشر بالثانية؛ رسوم التخزين أو البيانات قد تكون منفصلة.</i>")
    await callback.message.edit_text("\n".join(lines), reply_markup=main_menu())
