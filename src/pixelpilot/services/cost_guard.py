from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from html import escape

from aiogram import Bot

from pixelpilot.config import Settings
from pixelpilot.db import Database
from pixelpilot.domain import InstancePhase
from pixelpilot.services.orchestrator import Orchestrator


async def cost_guard_loop(
    bot: Bot,
    settings: Settings,
    db: Database,
    orchestrator: Orchestrator,
) -> None:
    """Warn about idle paid GPU time and optionally destroy idle instances."""
    while True:
        try:
            await _cost_guard_tick(bot, settings, db, orchestrator)
        except asyncio.CancelledError:
            raise
        except Exception:
            pass
        await asyncio.sleep(max(10, settings.cost_guard_poll_seconds))


async def _cost_guard_tick(
    bot: Bot,
    settings: Settings,
    db: Database,
    orchestrator: Orchestrator,
) -> None:
    instance_id = await db.get("instance.id")
    phase = await db.get("instance.phase", InstancePhase.NONE.value)
    if not instance_id or phase != InstancePhase.READY.value:
        return
    if await db.get("inference.active", False):
        return

    stamp = await db.get("instance.last_activity_at")
    if not stamp:
        return
    try:
        last = datetime.fromisoformat(str(stamp))
        if last.tzinfo is None:
            last = last.replace(tzinfo=UTC)
    except ValueError:
        return
    idle_minutes = (datetime.now(UTC) - last).total_seconds() / 60

    auto_after = settings.cost_guard_auto_destroy_minutes
    if auto_after > 0 and idle_minutes >= auto_after:
        try:
            destroyed = await orchestrator.destroy_current()
        except Exception as exc:
            await bot.send_message(
                settings.owner_telegram_id,
                f"⚠️ Cost Guard حاول حذف Instance <code>{instance_id}</code> وفشل:\n"
                f"<code>{escape(str(exc))}</code>",
            )
            return
        if destroyed:
            await bot.send_message(
                settings.owner_telegram_id,
                f"🛡 <b>Cost Guard</b>\nتم حذف Instance <code>{instance_id}</code> تلقائيًا "
                f"بعد {idle_minutes:.0f} دقيقة خمول.",
            )
        return

    warn_after = settings.cost_guard_warn_minutes
    if warn_after <= 0 or idle_minutes < warn_after:
        return
    warned_id = await db.get("cost_guard.warned_instance")
    warned_stamp = await db.get("cost_guard.warned_activity_at")
    if warned_id == instance_id and warned_stamp == stamp:
        return
    await bot.send_message(
        settings.owner_telegram_id,
        f"💸 <b>تنبيه تكلفة</b>\nInstance <code>{instance_id}</code> جاهز لكنه خامل منذ نحو "
        f"{idle_minutes:.0f} دقيقة.\nإذا انتهيت، استخدم 🗑 حذف السيرفر لإيقاف تكلفة الـInstance والتخزين.",
    )
    await db.set("cost_guard.warned_instance", instance_id)
    await db.set("cost_guard.warned_activity_at", stamp)
