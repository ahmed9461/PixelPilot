from __future__ import annotations

from html import escape

from aiogram import Router
from aiogram.types import CallbackQuery

from pixelpilot.bot.callbacks import safe_callback_answer
from pixelpilot.bot.keyboards import destroy_confirm_keyboard, main_menu, offer_confirm_keyboard, offers_keyboard
from pixelpilot.preflight import format_preflight, run_external_preflight, run_local_preflight
from pixelpilot.services.orchestrator import Orchestrator

router = Router(name="servers")
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
    text = format_preflight(checks)
    if all(item.ok for item in checks):
        try:
            offers = await orch().offers()
            text += f"\n\n✅ Vast API والبحث يعملان — {len(offers)} عرض مطابق حاليًا."
        except Exception as exc:
            text += f"\n\n❌ فشل اختبار Vast API: <code>{escape(str(exc))}</code>"
    await callback.message.edit_text(text, reply_markup=main_menu())


@router.callback_query(lambda q: q.data == "servers:search")
async def search(callback: CallbackQuery) -> None:
    await safe_callback_answer(callback, "جاري البحث...")
    await callback.message.edit_text("🔎 أبحث عن عروض Vast المناسبة لـ Qwen3-Omni...")
    try:
        offers = await orch().offers()
    except Exception as exc:
        await callback.message.edit_text(f"❌ فشل البحث:\n<code>{escape(str(exc))}</code>", reply_markup=main_menu())
        return
    if not offers:
        await callback.message.edit_text("لا توجد عروض مطابقة حاليًا. جرّب لاحقًا أو عدّل سياسة السعر/العتاد في الإعدادات.", reply_markup=main_menu())
        return
    await callback.message.edit_text(
        "🧾 <b>العروض المطابقة</b>\nالحد الافتراضي مضبوط لسيرفر بذاكرة GPU مناسبة لنسخة Qwen3-Omni BF16. اختر عرضًا لمراجعة التفاصيل:",
        reply_markup=offers_keyboard(offers),
    )


@router.callback_query(lambda q: q.data and q.data.startswith("servers:offer:"))
async def offer_details(callback: CallbackQuery) -> None:
    offer_id = int(callback.data.rsplit(":", 1)[1])
    offer = await orch().cached_offer(offer_id)
    await safe_callback_answer(callback)
    if offer is None:
        await callback.message.edit_text("العرض لم يعد موجودًا في آخر نتائج البحث.", reply_markup=main_menu())
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
        f"الموديل: <code>{escape(orch().settings.model_id)}</code>",
        "⚠️ عند الضغط على استئجار يبدأ احتساب Vast، ثم يقوم PixelPilot بتثبيت وتشغيل vLLM والموديل تلقائيًا.",
        "🖐 الحذف التلقائي عند فشل التجهيز مغلق افتراضيًا؛ تستطيع حذف الـInstance يدويًا من البوت.",
    ])
    await callback.message.edit_text("\n".join(lines), reply_markup=offer_confirm_keyboard(offer_id))


@router.callback_query(lambda q: q.data and q.data.startswith("servers:rent:"))
async def rent(callback: CallbackQuery) -> None:
    offer_id = int(callback.data.rsplit(":", 1)[1])
    await safe_callback_answer(callback, "بدء الاستئجار")
    await callback.message.edit_text("🚀 جاري إنشاء السيرفر...")

    async def progress(text: str) -> None:
        try:
            await callback.message.edit_text(f"⏳ <b>تجهيز PixelPilot</b>\n\n{text}")
        except Exception:
            pass

    try:
        result = await orch().rent_and_prepare(offer_id, progress=progress)
    except Exception as exc:
        await callback.message.edit_text(
            f"❌ فشل الاستئجار/التجهيز:\n<code>{escape(str(exc))}</code>\n\nالـInstance لن يُحذف تلقائيًا. راجع حالته ثم احذفه يدويًا عندما تريد إيقاف التكلفة.",
            reply_markup=main_menu(),
        )
        return
    await callback.message.edit_text(
        f"✅ <b>PixelPilot جاهز بالكامل</b>\nInstance: <code>{result['instance_id']}</code>\nModel: <code>{escape(orch().settings.model_id)}</code>\n\nأرسل الآن نصًا أو صورة أو تسجيلًا صوتيًا مباشرة للبوت.",
        reply_markup=main_menu(),
    )


@router.callback_query(lambda q: q.data == "servers:destroy_confirm")
async def destroy_confirm(callback: CallbackQuery) -> None:
    await safe_callback_answer(callback)
    await callback.message.edit_text(
        "⚠️ الحذف نهائي للـInstance وسيوقف تشغيل الموديل ويحذف الكاش الموجود على السيرفر المؤقت.\nهل أنت متأكد؟",
        reply_markup=destroy_confirm_keyboard(),
    )


@router.callback_query(lambda q: q.data == "servers:destroy")
async def destroy(callback: CallbackQuery) -> None:
    await safe_callback_answer(callback, "جاري الحذف...")
    try:
        destroyed = await orch().destroy_current()
    except Exception as exc:
        await callback.message.edit_text(f"❌ فشل الحذف:\n<code>{escape(str(exc))}</code>", reply_markup=main_menu())
        return
    text = "🗑 تم حذف السيرفر نهائيًا." if destroyed else "لا يوجد سيرفر حالي محفوظ."
    await callback.message.edit_text(text, reply_markup=main_menu())


@router.callback_query(lambda q: q.data == "servers:stop")
async def stop(callback: CallbackQuery) -> None:
    await safe_callback_answer(callback, "جاري الإيقاف...")
    try:
        stopped = await orch().stop_current()
    except Exception as exc:
        await callback.message.edit_text(f"❌ فشل الإيقاف:\n<code>{escape(str(exc))}</code>", reply_markup=main_menu())
        return
    text = "⏹ تم إيقاف السيرفر. تذكير: رسوم التخزين في Vast قد تستمر أثناء التوقف." if stopped else "لا يوجد سيرفر حالي."
    await callback.message.edit_text(text, reply_markup=main_menu())


@router.callback_query(lambda q: q.data == "servers:start")
async def start_instance(callback: CallbackQuery) -> None:
    await safe_callback_answer(callback, "جاري التشغيل...")
    await callback.message.edit_text("▶️ جاري تشغيل السيرفر والتحقق من Qwen3-Omni...")

    async def progress(text: str) -> None:
        try:
            await callback.message.edit_text(f"⏳ <b>إعادة التشغيل</b>\n\n{text}")
        except Exception:
            pass

    try:
        started = await orch().start_current(progress=progress)
    except Exception as exc:
        await callback.message.edit_text(f"❌ فشل التشغيل:\n<code>{escape(str(exc))}</code>", reply_markup=main_menu())
        return
    text = "✅ السيرفر والموديل جاهزان." if started else "لا يوجد سيرفر حالي."
    await callback.message.edit_text(text, reply_markup=main_menu())


@router.callback_query(lambda q: q.data == "servers:status")
async def status(callback: CallbackQuery) -> None:
    await safe_callback_answer(callback)
    try:
        state = await orch().current_state(probe_inference=True)
    except Exception as exc:
        await callback.message.edit_text(f"❌ تعذر قراءة الحالة:\n<code>{escape(str(exc))}</code>", reply_markup=main_menu())
        return
    if not state.get("instance_id"):
        await callback.message.edit_text("📊 لا يوجد سيرفر حالي.\nالحالة: <b>NONE</b>", reply_markup=main_menu())
        return
    lines = [
        f"📊 Instance: <code>{state['instance_id']}</code>",
        f"PixelPilot: <b>{escape(str(state.get('phase')))}</b>",
        f"Vast: <b>{escape(str(state.get('vast_status', '?')))}</b>",
        f"Model: <code>{escape(str(state.get('model_id', '?')))}</code>",
    ]
    offer = state.get("offer")
    if isinstance(offer, dict) and offer.get("price_per_hour") is not None:
        lines.append(f"السعر المتعاقد: <b>${float(offer['price_per_hour']):.3f}/ساعة</b>")
    if "inference_ready" in state:
        lines.append(f"Inference: <b>{'READY ✅' if state['inference_ready'] else 'NOT READY ⏳'}</b>")
    await callback.message.edit_text("\n".join(lines), reply_markup=main_menu())
