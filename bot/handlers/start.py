from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.main_menu import main_menu_kb
from database.models import Referral, User

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, user: User, session: AsyncSession) -> None:
    # Обробка реферального параметру: /start ref_123456
    args = message.text.split()
    if len(args) > 1 and args[1].startswith("ref_"):
        await _process_referral(session, user, args[1])

    vip_badge = "⭐ VIP • " if user.is_vip else ""
    text = (
        f"💼 <b>Ласкаво просимо, {user.first_name}!</b>\n"
        f"<i>{vip_badge}Affiliate & Earn Platform</i>\n\n"
        "📋 Виконуйте завдання — отримуйте реальні виплати.\n"
        "👥 Запрошуйте друзів — заробляйте на рефералах.\n"
        "⭐ Активуйте VIP — отримуйте завдання з підвищеною винагородою.\n\n"
        "<blockquote>Оберіть розділ у меню нижче 👇</blockquote>"
    )
    await message.answer(text, reply_markup=main_menu_kb(), parse_mode="HTML")


async def _process_referral(session: AsyncSession, user: User, ref_arg: str) -> None:
    try:
        referrer_id = int(ref_arg.replace("ref_", ""))
    except ValueError:
        return

    if referrer_id == user.id:
        return  # не можна запросити себе

    from sqlalchemy import select
    existing = await session.execute(
        select(Referral).where(Referral.referred_id == user.id)
    )
    if existing.scalar_one_or_none():
        return  # вже має реферера

    ref = Referral(referrer_id=referrer_id, referred_id=user.id)
    session.add(ref)
    user.referrer_id = referrer_id
    await session.commit()
