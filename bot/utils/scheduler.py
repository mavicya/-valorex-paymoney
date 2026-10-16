import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from database.engine import async_session_factory
from services.vip_service import expire_vip_subscriptions

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(timezone="UTC")


@scheduler.scheduled_job("interval", minutes=10, id="expire_vip")
async def job_expire_vip() -> None:
    """Кожні 10 хв скидає VIP-статус для прострочених підписок."""
    async with async_session_factory() as session:
        count = await expire_vip_subscriptions(session)
        if count:
            logger.info("VIP expired for %d user(s)", count)
