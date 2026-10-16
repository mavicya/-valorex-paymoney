"""
VIP Service — вся бізнес-логіка підписок.

АРХІТЕКТУРА ТРАНЗАКЦІЙ:
  Ці функції НЕ викликають session.begin() і НЕ роблять session.commit().
  Причина: middleware вже відкриває autobegin-транзакцію через SELECT.
  Повторний begin() кидає InvalidRequestError.

  Правило: session.flush() для отримання id → commit() викликає handler.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from config import VIP_PLANS
from database.models import User, VIPSubscription


async def activate_vip(
    session: AsyncSession,
    user_id: int,
    days: int,
    payment_method: str,           # 'stars' | 'balance' | 'admin'
    amount_paid: Decimal = Decimal("0"),
    stars_paid: int | None = None,
    granted_by_admin: bool = False,
) -> VIPSubscription:
    """
    Активує або подовжує VIP. Повертає VIPSubscription.
    Викидає ValueError("insufficient_balance") якщо недостатньо коштів.
    COMMIT робить caller (handler).
    """
    now = datetime.now(tz=timezone.utc)

    result = await session.execute(
        select(User).where(User.id == user_id).with_for_update()
    )
    user: User = result.scalar_one()

    if payment_method == "balance":
        price = Decimal(str(VIP_PLANS[days]["uah"]))
        if user.balance < price:
            raise ValueError("insufficient_balance")
        user.balance -= price
        amount_paid = price

    base = max(user.vip_expires_at or now, now)
    new_expires = base + timedelta(days=days)

    user.is_vip = True
    user.vip_expires_at = new_expires

    sub = VIPSubscription(
        user_id=user_id,
        duration_days=days,
        payment_method=payment_method,
        amount_paid=amount_paid,
        stars_paid=stars_paid,
        activated_at=now,
        expires_at=new_expires,
        granted_by_admin=granted_by_admin,
    )
    session.add(sub)
    await session.flush()   # отримуємо sub.id без commit — commit робить handler
    return sub


async def revoke_vip(session: AsyncSession, user_id: int) -> None:
    """Знімає VIP. COMMIT робить caller."""
    await session.execute(
        update(User)
        .where(User.id == user_id)
        .values(is_vip=False, vip_expires_at=None)
    )


async def expire_vip_subscriptions(session: AsyncSession) -> int:
    """
    Scheduler-функція: скидає is_vip=False для прострочених підписок.
    Scheduler сам передає власну сесію та робить commit.
    """
    result = await session.execute(
        update(User)
        .where(
            User.is_vip == True,
            User.vip_expires_at <= datetime.now(tz=timezone.utc),
        )
        .values(is_vip=False)
        .returning(User.id)
    )
    await session.commit()
    return len(result.all())
