import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage

from bot.handlers import admin, profile, start, tasks, vip, withdrawals
from bot.middlewares.auth import AuthMiddleware
from bot.utils.scheduler import scheduler
from config import settings
from database.engine import init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)


async def main() -> None:
    await init_db()

    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    storage = RedisStorage.from_url(settings.REDIS_URL)
    dp = Dispatcher(storage=storage)

    # ── Middlewares ──
    dp.message.middleware(AuthMiddleware())
    dp.callback_query.middleware(AuthMiddleware())

    # ── Routers ──
    dp.include_router(admin.router)       # першим — щоб адмін-команди мали пріоритет
    dp.include_router(start.router)
    dp.include_router(vip.router)
    dp.include_router(tasks.router)
    dp.include_router(profile.router)
    dp.include_router(withdrawals.router)

    # ── Scheduler ──
    scheduler.start()
    logging.info("Scheduler started")

    try:
        logging.info("Bot polling started")
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        scheduler.shutdown()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
