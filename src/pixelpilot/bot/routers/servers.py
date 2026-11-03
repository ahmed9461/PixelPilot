from __future__ import annotations

import asyncio
import logging
from html import escape
from typing import Any

from aiogram import Router
from aiogram.types import CallbackQuery, Message

from pixelpilot.bot.callbacks import safe_callback_answer, safe_edit_text
from pixelpilot.bot.keyboards import destroy_confirm_keyboard, main_menu, offer_confirm_keyboard, offers_keyboard
from pixelpilot.preflight import run_external_preflight, run_local_preflight
from pixelpilot.pricing import offer_cost_lines, offer_quality_rank
from pixelpilot.domain import GpuOffer
from pixelpilot.services.offer_policy import network_tier, NETWORK_LABELS, eligible, quote_fingerprint
from pixelpilot.services.orchestrator import (
    OfferChangedError,
    OfferUnavailableError,
    Orchestrator,
    RentRejectedError,
)

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


def _selected_offer(data: str) -> tuple[int, bool, bool]:
    parts = data.split(":")
    suffix = parts[3] if len(parts) > 3 else "a"
    try:
        offer_id = int(parts[2])
    except (IndexError, ValueError):
        offer_id = 0
    return offer_id, suffix == "p", suffix == "h"


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
    if not instance_id and (_lifecycle_busy() or phase == "renting" or await orch().db.get("instance.pending_label")):
        await safe_edit_text(callback.message,
            "⏳ <b>طلب الاستئجار لم يُحسم بعد</b>\n\n"
            "لم يصل رقم الـInstance المؤكد، لذلك لن ألغي محاولة قد تترك "
            "سيرفرًا مدفوعًا بدون تتبع. افحص الحالة وانتظر ظهور رقمه ثم استخدم "
            "الإيقاف أو الحذف.",
            reply_markup=main_menu(),
        )
        return False

    if instance_id:
        await orch().wait_for_control_idle()
        await _cancel_lifecycle_if_running()
    return True


def _offer_signature(item: Any) -> tuple[Any, ...]:
    if isinstance(item, dict):
        return (
            int(item.get("offer_id") or 0),
            round(float(item.get("price_per_hour") or 0.0), 6),
            round(float(item.get("reliability") or 0.0), 6),
            round(float(item.get("inet_down_mbps") or 0.0), 3),
            round(float(item.get("inet_up_mbps") or 0.0), 3),
            str(item.get("gpu_name") or ""),
            item.get("download_usd_per_gb"),
            item.get("upload_usd_per_gb"),
        )
    return (
        int(item.offer_id),
        round(float(item.price_per_hour), 6),
        round(float(item.reliability or 0.0), 6),
        round(float(item.inet_down_mbps or 0.0), 3),
        round(float(item.inet_up_mbps or 0.0), 3),
        str(item.gpu_name),
        getattr(item, "download_usd_per_gb", None),
        getattr(item, "upload_usd_per_gb", None),
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
    label = "تقدير مدة التشغيل بعد الحذف" if final else "تقدير مدة التشغيل فقط"
    return [
        f"⏱ وقت التشغيل المحتسب: <b>{_format_duration(active_seconds)}</b>",
        f"💵 {label}: <b>${cost:.4f}</b>",
        "<i>ليس إجمالي فاتورة Vast؛ لا يشمل رسوم Download/Upload أو التخزين أثناء الإيقاف.</i>",
    ]


@router.callback_query(lambda q: q.data == "servers:preflight")
async def preflight(callback: CallbackQuery) -> None:
    await safe_callback_answer(callback, "جاري الفحص...")
    await safe_edit_text(
        callback.message,
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
        await safe_edit_text(callback.message,
            "❌ <b>يوجد خلل في الجاهزية</b>\n\n"
            + "\n".join(failed),
            reply_markup=main_menu(),
        )
        return

    await safe_edit_text(callback.message,
        "✅ <b>فحص الجاهزية ناجح</b>\n\n"
        "الإعدادات ومصدر المشروع والوصول إلى Qwen سليمة. "
        "البحث عن عروض Vast أصبح منفصلًا حتى يبقى هذا الفحص سريعًا.",
        reply_markup=main_menu(),
    )


async def _search_offers(
    callback: CallbackQuery, *, preferred_only: bool, premium_only: bool = False,
) -> None:
    mode = "premium" if premium_only else ("preferred" if preferred_only else "all")
    await safe_callback_answer(callback, "جاري التحديث...")
    loading = (
        "🚀 أبحث عن أفضل سيرفرات 80GB+..."
        if premium_only else (
            "🔥 أبحث عن سيرفرات 48GB+ المتاحة..."
            if preferred_only else f"🔎 أقارن موثوقية المضيف والشبكة ورسوم التنزيل حتى ${orch().settings.vast_max_price_usd_hour:.2f}/ساعة..."
        )
    )
    await safe_edit_text(callback.message, loading)

    previous_mode = str(await orch().db.get("offers.search_mode", "all") or "all")
    previous = await orch().db.get("offers.last", [])
    if previous_mode != mode or not isinstance(previous, list):
        previous = []

    try:
        offers = await orch().offers(preferred_only=preferred_only, premium_only=premium_only)
    except Exception:
        logger.exception("Server offer search failed")
        await safe_edit_text(callback.message,
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
    premium_count = int(await orch().db.get("offers.premium_candidate_count", 0) or 0)

    if not offers:
        scope = (
            f"لا توجد عروض 80GB+ تحت سقف ${orch().settings.vast_max_price_usd_hour:.2f} حاليًا."
            if premium_only else (
                "لا توجد عروض 48GB+ مطابقة للفلاتر والسقف."
                if preferred_only else "لا توجد عروض مناسبة ضمن الميزانية وجودة الشبكة المحددة."
            )
        )
        fallback = await orch().db.get("offers.fallback", [])
        if fallback:
            scope += "\n\n⚠️ عروض احتياطية أقل من الحد الافتراضي للشبكة — للعرض فقط، دون زر استئجار:\n"
            for row in fallback:
                x = GpuOffer(**row)
                scope += f"\n{escape(x.gpu_name)} {x.gpu_ram_gb:.0f}GB | ${x.price_per_hour:.3f}/h | ↓{x.inet_down_mbps or 0:.0f}/↑{x.inet_up_mbps or 0:.0f} Mbps | #{x.offer_id}"
        await safe_edit_text(callback.message,
            f"🔄 <b>تحديث السوق #{refresh_no}</b>\n\n{scope}",
            reply_markup=offers_keyboard([], preferred_only=preferred_only, premium_only=premium_only),
        )
        return

    note = _refresh_note(previous, offers, refresh_no)
    await orch().db.set("offers.last_refresh_note", note)

    if premium_only:
        title = "🚀 <b>عروض 80GB+ ضمن الميزانية</b>"
        discovery = f"المرشحون المطابقون: <b>{candidate_count}</b>"
    elif preferred_only:
        title = "🔥 <b>عروض 48GB+ المتاحة</b>"
        discovery = f"المرشحون المطابقون: <b>{candidate_count}</b>"
    else:
        title = "⚡ <b>أفضل السيرفرات حسب القوة والشبكة والتكلفة</b>"
        discovery = (
            f"المرشحون المطابقون: <b>{candidate_count}</b> "
            f"— 48GB+: <b>{preferred_count}</b> — 80GB+: <b>{premium_count}</b>"
        )

    settings = orch().settings
    comparison = (
        f"سقف الإيجار الصارم: <b>${settings.vast_max_price_usd_hour:.2f}/ساعة</b>. "
        f"نت مطلوب ↓{settings.vast_min_inet_down_mbps:g}/↑{settings.vast_min_inet_up_mbps:g} Mbps.\n"
        f"المقارنة بين المرشحين: تنزيل مفترض <b>{settings.vast_estimated_download_gb:g} GB</b> "
        f"+ <b>{settings.vast_cost_comparison_hours:g} ساعة</b> تشغيل.\n"
        "الترتيب يعطي أولوية للأداء والنت والموثوقية، مع تقدير رسوم التنزيل؛ السرعات معلنة وليست قياسات فعلية."
    )
    if settings.vast_max_download_usd_per_tb is not None:
        comparison += f"\nسقف Download: <b>${settings.vast_max_download_usd_per_tb:g}/TB</b>."
    await safe_edit_text(callback.message,
        f"{title}\n{note}\n"
        f"{discovery}\n"
        f"المعروض لك الآن: <b>{len(offers)}</b>\n\n"
        f"{comparison}\n\n"
        + "\n".join(f"• {escape(x.gpu_name)} {x.gpu_ram_gb:.0f}GB | ↓{x.inet_down_mbps or 0:.0f}/↑{x.inet_up_mbps or 0:.0f} Mbps | {NETWORK_LABELS[network_tier(x)]} | DLPerf {x.dlperf or 0:.1f}" for x in offers)
        + "\n\nاختر عرضًا لمراجعة السعر ورسوم البيانات والمواصفات:",
        reply_markup=offers_keyboard(offers, preferred_only=preferred_only, premium_only=premium_only),
    )


@router.callback_query(lambda q: q.data == "servers:search")
async def search(callback: CallbackQuery) -> None:
    await _search_offers(callback, preferred_only=False)


@router.callback_query(lambda q: q.data == "servers:search80")
async def search_premium(callback: CallbackQuery) -> None:
    await _search_offers(callback, preferred_only=False, premium_only=True)


@router.callback_query(lambda q: q.data == "servers:search48")
async def search_preferred(callback: CallbackQuery) -> None:
    await _search_offers(callback, preferred_only=True)


@router.callback_query(lambda q: q.data and q.data.startswith("servers:offer:"))
async def offer_details(callback: CallbackQuery) -> None:
    offer_id, preferred_only, premium_only = _selected_offer(callback.data)
    offer = await orch().cached_offer(offer_id)
    await safe_callback_answer(callback)
    if offer is None or not eligible(offer, orch().settings):
        await safe_edit_text(callback.message,
            "العرض لم يعد موجودًا في آخر نتائج البحث.",
            reply_markup=main_menu(),
        )
        return

    lines = [
        "🖥 <b>تفاصيل العرض</b>",
        f"Offer ID: <code>{offer.offer_id}</code>",
        f"GPU: <b>{escape(offer.gpu_name)}</b>",
        f"VRAM: <b>{offer.gpu_ram_gb:.0f} GB</b>",
        f"السعر مع القرص المخصص: <b>${offer.price_per_hour:.3f}/ساعة</b>",
        f"الموثوقية: <b>{'?' if offer.reliability is None else f'{offer.reliability * 100:.1f}%'} </b>",
    ]
    profile = (
        "🚀 مناسب لوضع GPU الكامل و2K"
        if offer.gpu_ram_gb >= orch().settings.vast_preferred_gpu_ram_gb
        else "💡 يعمل بوضع توفير الذاكرة، ويفضّل معه القياسي"
    )
    lines.append(f"ملف التشغيل: <b>{profile}</b>")
    lines.append(f"جودة الشبكة: <b>{NETWORK_LABELS[network_tier(offer)]}</b> (معلنة)")
    settings = orch().settings
    score = -offer_quality_rank(
        offer, hourly_cap=settings.vast_max_price_usd_hour,
        download_gb=settings.vast_estimated_download_gb,
        billed_hours=settings.vast_cost_comparison_hours,
        preferred_down_mbps=settings.vast_preferred_inet_down_mbps,
        preferred_up_mbps=settings.vast_preferred_inet_up_mbps,
    )[1]
    lines.append(f"تقييم المقارنة التقريبي: <b>{score:.1f}</b> نقطة (ليس اختبار أداء فعليًا)")
    if offer.inet_down_mbps:
        lines.append(f"⬇️ سرعة التنزيل المعلنة: <b>{offer.inet_down_mbps:.0f} Mbps</b>")
    if offer.inet_up_mbps:
        lines.append(f"⬆️ سرعة الرفع المعلنة: <b>{offer.inet_up_mbps:.0f} Mbps</b>")
    if offer.compute_cap is not None:
        lines.append(f"CUDA compute capability: <b>{offer.compute_cap/100:g}</b>")
    if offer.total_flops is not None:
        lines.append(f"TFLOPs المعلنة: <b>{offer.total_flops:.1f}</b>")
    if offer.gpu_mem_bw is not None:
        lines.append(f"عرض نطاق ذاكرة GPU المعلن: <b>{offer.gpu_mem_bw:.1f} GB/s</b>")
    if offer.dlperf is not None:
        lines.append(f"⚡ مؤشر DLPerf المعلن: <b>{offer.dlperf:.1f}</b>")
    if offer.location:
        lines.append(f"الموقع: <b>{escape(offer.location)}</b>")
    lines.append("")
    lines.extend(offer_cost_lines(
        offer,
        download_gb=orch().settings.vast_estimated_download_gb,
        billed_hours=orch().settings.vast_cost_comparison_hours,
    ))
    lines.extend([
        "",
        "⚠️ تُحسب مدة التشغيل من الاستئجار؛ رسوم البيانات مستقلة، وقد يستمر التخزين بعد الإيقاف حتى الحذف.",
    ])
    await safe_edit_text(callback.message,
        "\n".join(lines),
        reply_markup=offer_confirm_keyboard(
            offer_id,
            preferred_only=preferred_only,
            premium_only=premium_only,
            quote=quote_fingerprint(offer),
        ),
    )


async def _rent_and_prepare_background(
    offer_id: int,
    status_message: Message,
    *,
    preferred_only: bool,
    premium_only: bool = False,
    expected_quote: str | None = None,
) -> None:
    async def progress(_text: str) -> None:
        try:
            state = await orch().current_state(probe_inference=False)
            billing = state.get("billing") if isinstance(state, dict) else None
            lines = [
                "⏳ <b>جاري تجهيز محرك الدردشة...</b>",
                escape(_text),
                "",
                "التجهيز يعمل في الخلفية؛ تستطيع استخدام أزرار الحالة والحذف أثناء ذلك.",
            ]
            lines.extend(_billing_lines(billing))
            await safe_edit_text(status_message, "\n".join(lines))
        except Exception:
            pass

    try:
        await orch().rent_and_prepare(offer_id, progress=progress, **({"expected_quote": expected_quote} if expected_quote else {}))
    except asyncio.CancelledError:
        raise
    except (OfferUnavailableError, OfferChangedError, RentRejectedError) as exc:
        logger.info("Vast rental did not start for offer %s: %s", offer_id, exc)
        try:
            await safe_edit_text(status_message,
                "❌ <b>لم يبدأ الاستئجار</b>\n\n"
                f"{escape(str(exc))}",
                reply_markup=offers_keyboard(
                    [],
                    preferred_only=preferred_only,
                    premium_only=premium_only,
                ),
            )
        except Exception:
            pass
        return
    except Exception:
        logger.exception("Server rent/provision failed")
        current_id = await orch().db.get("instance.id")
        pending_label = await orch().db.get("instance.pending_label")
        if current_id:
            text = (
                "❌ <b>تعذر تجهيز السيرفر</b>\n\n"
                "تم إنشاء Instance أو استعادته، لكن التجهيز لم يكتمل. "
                "استخدم «حالة السيرفر» أو احذفه لإيقاف التكلفة."
            )
        elif pending_label:
            text = (
                "⚠️ <b>تعذر تأكيد الاستئجار</b>\n\n"
                "لم يصل رقم Instance مؤكد من Vast. احتفظنا بمعرّف "
                "المحاولة لتفادي فقدان سيرفر قد يكون أُنشئ رغم انقطاع الرد."
            )
        else:
            text = (
                "❌ <b>لم يبدأ الاستئجار</b>\n\n"
                "تعذر التحقق من السوق أو بدء الطلب مع Vast. "
                "لم يتم تسجيل Instance مؤكد؛ أعد تحديث العروض ثم حاول مرة أخرى."
            )
        try:
            await safe_edit_text(status_message, text, reply_markup=main_menu())
        except Exception:
            pass
        return

    try:
        state = await orch().current_state(probe_inference=False)
        lines = [
            "✅ <b>محرك الدردشة وفهم الصور جاهز</b>",
            "محرك إنشاء وتعديل الصور يُحمّل عند أول طلب؛ لم يُفحص بعد على هذا السيرفر.",
            "",
            "أرسل سؤالًا للدردشة، أو صورة لفهمها؛ اختر وضع الصور لإنشائها أو تعديلها.",
        ]
        lines.extend(_billing_lines(state.get("billing")))
        await safe_edit_text(status_message, "\n".join(lines), reply_markup=main_menu())
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

    offer_id, preferred_only, premium_only = _selected_offer(callback.data)
    # Claim the lifecycle slot synchronously, before any Telegram/SQLite await.
    _track_lifecycle(
        _rent_from_callback(callback, offer_id, preferred_only, premium_only), name="pixelpilot-rent-and-prepare"
    )


async def _rent_from_callback(callback: CallbackQuery, offer_id: int, preferred_only: bool, premium_only: bool = False) -> None:
    parts = (callback.data or "").split(":")
    if len(parts) != 5 or len(parts[4]) != 12:
        await safe_callback_answer(callback, "افتح تفاصيل العرض الحالية قبل التأكيد", show_alert=True)
        return
    await safe_callback_answer(callback, "أتحقق من العرض ثم أبدأ التجهيز")
    await safe_edit_text(callback.message,
        "🔎 <b>جاري التحقق من العرض وبدء الاستئجار</b>\n\n"
        "أتحقق أولًا من نفس Offer ID في السوق الحي، ثم يبدأ التجهيز بالخلفية.",
        reply_markup=main_menu(),
    )
    status_message = await callback.message.answer(
        "⏳ <b>جاري بدء التجهيز...</b>"
    )
    await _rent_and_prepare_background(
        offer_id, status_message, preferred_only=preferred_only, premium_only=premium_only, expected_quote=parts[4]
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
    await safe_edit_text(callback.message,
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
        await safe_edit_text(callback.message,
            "❌ تعذر حذف السيرفر الآن. جرّب مرة أخرى.",
            reply_markup=main_menu(),
        )
        return
    if not destroyed:
        await safe_edit_text(callback.message, "لا يوجد سيرفر حالي.", reply_markup=main_menu())
        return
    billing = await orch().last_billing_snapshot()
    lines = ["🗑 تم حذف السيرفر نهائيًا."]
    lines.extend(_billing_lines(billing, final=True))
    await safe_edit_text(callback.message, "\n".join(lines), reply_markup=main_menu())


@router.callback_query(lambda q: q.data == "servers:stop")
async def stop(callback: CallbackQuery) -> None:
    await safe_callback_answer(callback, "جاري الإيقاف...")
    if not await _prepare_manual_control(callback):
        return
    try:
        stopped = await orch().stop_current()
    except Exception:
        logger.exception("Server stop failed")
        await safe_edit_text(callback.message,
            "❌ تعذر إيقاف السيرفر الآن.",
            reply_markup=main_menu(),
        )
        return
    if not stopped:
        await safe_edit_text(callback.message, "لا يوجد سيرفر حالي.", reply_markup=main_menu())
        return
    state = await orch().current_state(probe_inference=False)
    lines = ["⏹ تم إيقاف السيرفر. قد تستمر رسوم التخزين أثناء الإيقاف."]
    lines.extend(_billing_lines(state.get("billing")))
    await safe_edit_text(callback.message, "\n".join(lines), reply_markup=main_menu())


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
            await safe_edit_text(status_message, "\n".join(lines))
        except Exception:
            pass

    try:
        started = await orch().start_current(progress=progress)
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("Server start failed")
        try:
            await safe_edit_text(status_message,
                "❌ تعذر تشغيل السيرفر الآن.",
                reply_markup=main_menu(),
            )
        except Exception:
            pass
        return

    if not started:
        await safe_edit_text(status_message,
            "لا يوجد سيرفر حالي.",
            reply_markup=main_menu(),
        )
        return

    state = await orch().current_state(probe_inference=False)
    lines = ["✅ السيرفر جاهز."]
    lines.extend(_billing_lines(state.get("billing")))
    await safe_edit_text(status_message, "\n".join(lines), reply_markup=main_menu())


@router.callback_query(lambda q: q.data == "servers:start")
async def start_instance(callback: CallbackQuery) -> None:
    if _lifecycle_busy():
        await safe_callback_answer(
            callback,
            "يوجد تجهيز أو تشغيل جارٍ بالفعل",
            show_alert=True,
        )
        return

    _track_lifecycle(_start_from_callback(callback), name="pixelpilot-start-instance")


async def _start_from_callback(callback: CallbackQuery) -> None:
    await safe_callback_answer(callback, "بدأ التشغيل بالخلفية")
    await safe_edit_text(callback.message,
        "▶️ <b>بدأ تشغيل السيرفر</b>\n\n"
        "يمكنك متابعة الحالة أثناء التشغيل.",
        reply_markup=main_menu(),
    )
    status_message = await callback.message.answer("⏳ جاري تشغيل السيرفر...")
    await _start_background(status_message)


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
    await safe_edit_text(
        callback.message,
        "📊 <b>جاري قراءة حالة السيرفر...</b>",
        reply_markup=main_menu(),
    )
    try:
        state = await orch().current_state(probe_inference=True)
    except Exception:
        logger.exception("Server status check failed")
        await safe_edit_text(callback.message,
            "❌ تعذر قراءة حالة السيرفر الآن.",
            reply_markup=main_menu(),
        )
        return

    if not state.get("instance_id"):
        phase = str(state.get("phase") or "none")
        if state.get("pending_label"):
            body = "⚠️ نتيجة الاستئجار غير مؤكدة. تتم مطابقة الطلب مع Vast؛ لا تبدأ استئجارًا آخر حتى يظهر رقم السيرفر أو تتأكد من عدم إنشائه."
        elif phase == "none":
            body = "لا يوجد سيرفر حالي."
        else:
            body = _status_label(state)
        await safe_edit_text(callback.message,
            f"📊 <b>حالة السيرفر</b>\n\n{body}",
            reply_markup=main_menu(),
        )
        return

    lines = [
        "📊 <b>حالة السيرفر</b>",
        "",
        _status_label(state),
    ]
    capabilities = state.get("capabilities")
    if isinstance(capabilities, dict):
        for key, name in [("chat", "الدردشة"), ("vision", "فهم الصور"), ("image", "إنشاء وتعديل الصور")]:
            lines.append(f"{name}: {'محمّل' if capabilities.get(key) else 'غير محمّل؛ عند الطلب'}")
    progress = state.get("progress")
    if isinstance(progress, dict): lines.append(f"المرحلة: {escape(str(progress.get('stage', 'unknown')))}")
    offer = state.get("offer")
    if isinstance(offer, dict) and offer.get("price_per_hour") is not None:
        lines.append(f"السعر: <b>${float(offer['price_per_hour']):.3f}/ساعة</b>")
    lines.extend(_billing_lines(state.get("billing")))
    await safe_edit_text(callback.message, "\n".join(lines), reply_markup=main_menu())
