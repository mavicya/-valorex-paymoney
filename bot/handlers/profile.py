from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import TaskSubmission, User

router = Router()


@router.message(F.text == "👤 Профіль")
async def show_profile(message: Message, user: User, session: AsyncSession) -> None:
    # Кількість виконаних завдань
    count_result = await session.execute(
        select(func.count()).where(
            TaskSubmission.user_id == user.id,
            TaskSubmission.status == "approved",
        )
    )
    completed = count_result.scalar_one()

    # VIP-рядок
    vip_line = _build_vip_line(user)

    # Реферальне посилання
    bot_info = await message.bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start=ref_{user.id}"

    text = (
        f"👤 <b>Профіль</b>\n\n"
        f"🆔 ID: <code>{user.id}</code>\n"
        f"👤 Username: @{user.username or '—'}\n\n"
        f"💰 Баланс: <code>{user.balance:.2f} UAH</code>\n"
        f"📊 Всього зароблено: <code>{user.total_earned:.2f} UAH</code>\n"
        f"✅ Виконано завдань: <code>{completed}</code>\n"
        f"{vip_line}\n\n"
        f"🔗 Реферальне посилання:\n"
        f"<code>{ref_link}</code>"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Вивести кошти",  callback_data="withdraw_start")],
        [InlineKeyboardButton(text="⭐ Купити / Продовжити VIP", callback_data="vip_plans")],
    ])

    await message.answer(text, reply_markup=kb, parse_mode="HTML")


def _build_vip_line(user: User) -> str:
    if not user.is_vip or not user.vip_expires_at:
        return "⭐ VIP: —"

    now    = datetime.now(tz=timezone.utc)
    delta  = user.vip_expires_at - now
    days   = delta.days
    hours  = delta.seconds // 3600
    exp_str = user.vip_expires_at.strftime("%d.%m.%Y %H:%M")

    return (
        f"⭐ VIP: <b>Активний</b>\n"
        f"   └ до {exp_str} (залишилось {days}д {hours}г)"
    )
