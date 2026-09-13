from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from pixelpilot.bot.middleware import OwnerOnlyMiddleware
from pixelpilot.bot.routers import generate, home, servers
from pixelpilot.config import get_settings
from pixelpilot.db import Database
from pixelpilot.services.cost_guard import cost_guard_loop
from pixelpilot.services.orchestrator import Orchestrator
from pixelpilot.services.vast_gateway import VastSdkGateway


async def main() -> None:
    settings = get_settings()
    settings.validate_runtime()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    db = Database(settings.database_path)
    await db.init()
    vast = VastSdkGateway(settings.vast_api_key, worker_proxy_port=settings.worker_proxy_port)
    orchestrator = Orchestrator(settings, db, vast)
    servers.configure(orchestrator)
    generate.configure(orchestrator)

    bot = Bot(settings.telegram_bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.update.middleware(OwnerOnlyMiddleware(settings.owner_telegram_id))
    dp.include_router(home.router)
    dp.include_router(servers.router)
    dp.include_router(generate.router)

    recovery_task = asyncio.create_task(orchestrator.recover_current(), name="pixelpilot-recovery")
    guard_task = asyncio.create_task(cost_guard_loop(bot, settings, db, orchestrator), name="pixelpilot-cost-guard")
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        for task in (recovery_task, guard_task):
            task.cancel()
        await asyncio.gather(recovery_task, guard_task, return_exceptions=True)
        await bot.session.close()


def run() -> None:
    asyncio.run(main())


if __name__ == "__main__":
    run()
