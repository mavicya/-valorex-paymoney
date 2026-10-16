"""
Admin handlers.

ТРАНЗАКЦІЇ: session.begin() НЕ використовується (middleware вже відкриває autobegin).
Всі зміни в БД фіксуються через await session.commit() в кінці кожного handler.
"""
from datetime import datetime, timezone
from decimal import Decimal

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.states import AdminBroadcastFlow
from config import settings
from database.models import Task, TaskSubmission, User, Withdrawal  # Task: used in stats only
from services.vip_service import activate_vip, revoke_vip

router = Router()


def _is_admin(user_id: int) -> bool:
    return user_id in settings.ADMIN_IDS


# ─────────────────────────────────────────────
# /stats
# ─────────────────────────────────────────────
@router.message(Command("stats"))
async def cmd_stats(message: Message, session: AsyncSession) -> None:
    if not _is_admin(message.from_user.id):
        return

    total_users  = (await session.execute(select(func.count(User.id)))).scalar_one()
    active_vip   = (await session.execute(select(func.count(User.id)).where(User.is_vip == True))).scalar_one()
    pending_subs = (await session.execute(select(func.count(TaskSubmission.id)).where(TaskSubmission.status == "pending"))).scalar_one()
    pending_wd   = (await session.execute(select(func.count(Withdrawal.id)).where(Withdrawal.status == "pending"))).scalar_one()
    total_paid   = (await session.execute(
        select(func.coalesce(func.sum(Withdrawal.amount), 0)).where(Withdrawal.status == "approved")
    )).scalar_one()

    await message.answer(
        "📊 <b>Статистика платформи</b>\n\n"
        f"👥 Юзерів: <code>{total_users}</code>\n"
        f"⭐ Активних VIP: <code>{active_vip}</code>\n"
        f"⏳ Завдань на перевірці: <code>{pending_subs}</code>\n"
        f"💳 Запитів на вивід: <code>{pending_wd}</code>\n"
        f"💰 Всього виплачено: <code>{float(total_paid):.2f} UAH</code>",
        parse_mode="HTML",
    )
    # Тільки SELECT — commit не потрібен


# ─────────────────────────────────────────────
# /balance [user_id] [+-amount]
# ─────────────────────────────────────────────
@router.message(Command("balance"))
async def cmd_balance(message: Message, session: AsyncSession) -> None:
    if not _is_admin(message.from_user.id):
        return

    parts = message.text.split()
    if len(parts) != 3:
        await message.answer("Формат: <code>/balance [user_id] [+-amount]</code>", parse_mode="HTML")
        return

    try:
        target_id = int(parts[1])
        delta     = Decimal(parts[2])
    except ValueError:
        await message.answer("❌ Невірний формат.")
        return

    result = await session.execute(
        select(User).where(User.id == target_id).with_for_update()
    )
    user = result.scalar_one_or_none()

    if not user:
        await message.answer(f"❌ Юзер <code>{target_id}</code> не знайдений.", parse_mode="HTML")
        return

    user.balance += delta
    if delta > 0:
        user.total_earned += delta

    await session.commit()                                  # ← commit

    sign = "+" if delta >= 0 else ""
    await message.answer(
        f"✅ Баланс юзера <code>{target_id}</code> змінено на <b>{sign}{delta} UAH</b>.",
        parse_mode="HTML",
    )
    try:
        await message.bot.send_message(
            target_id,
            f"💰 {'Ваш баланс поповнено на' if delta > 0 else 'З вашого балансу знято'} "
            f"<code>{abs(delta)} UAH</code>.",
            parse_mode="HTML",
        )
    except Exception:
        pass


# ─────────────────────────────────────────────
# /vip [user_id] [days]   (0 = забрати)
# ─────────────────────────────────────────────
@router.message(Command("vip"))
async def cmd_vip(message: Message, session: AsyncSession) -> None:
    if not _is_admin(message.from_user.id):
        return

    parts = message.text.split()
    if len(parts) != 3:
        await message.answer(
            "Формат: <code>/vip [user_id] [days]</code>  (days=0 → забрати VIP)",
            parse_mode="HTML",
        )
        return

    try:
        target_id = int(parts[1])
        days      = int(parts[2])
    except ValueError:
        await message.answer("❌ Невірний формат.")
        return

    if days == 0:
        await revoke_vip(session, target_id)
        await session.commit()                              # ← commit
        await message.answer(f"✅ VIP знято з юзера <code>{target_id}</code>.", parse_mode="HTML")
        try:
            await message.bot.send_message(target_id, "ℹ️ Ваш VIP-статус скасовано адміністратором.")
        except Exception:
            pass
    else:
        sub = await activate_vip(
            session, target_id, days,
            payment_method="admin",
            granted_by_admin=True,
        )
        await session.commit()                              # ← commit
        exp_str = sub.expires_at.strftime("%d.%m.%Y %H:%M")
        await message.answer(
            f"✅ VIP видано юзеру <code>{target_id}</code> до <b>{exp_str}</b>.",
            parse_mode="HTML",
        )
        try:
            await message.bot.send_message(
                target_id,
                f"⭐ <b>Вам видано VIP!</b>\n\nСтатус активний до {exp_str} UTC.",
                parse_mode="HTML",
            )
        except Exception:
            pass


# ─────────────────────────────────────────────
# /vipstatus [user_id]
# ─────────────────────────────────────────────
@router.message(Command("vipstatus"))
async def cmd_vipstatus(message: Message, session: AsyncSession) -> None:
    if not _is_admin(message.from_user.id):
        return

    parts = message.text.split()
    if len(parts) != 2:
        await message.answer("Формат: <code>/vipstatus [user_id]</code>", parse_mode="HTML")
        return

    result = await session.execute(select(User).where(User.id == int(parts[1])))
    user   = result.scalar_one_or_none()

    if not user:
        await message.answer("❌ Юзер не знайдений.")
        return

    if user.is_vip and user.vip_expires_at:
        exp_str = user.vip_expires_at.strftime("%d.%m.%Y %H:%M")
        await message.answer(f"⭐ VIP активний до {exp_str} UTC")
    else:
        await message.answer("ℹ️ VIP не активний.")


# ─────────────────────────────────────────────
# ВЕРИФІКАЦІЯ ЗАВДАНЬ  ✅ / ❌
# ─────────────────────────────────────────────
@router.callback_query(F.data.startswith("sub_approve:"))
async def cb_approve(callback: CallbackQuery, session: AsyncSession) -> None:
    if not _is_admin(callback.from_user.id):
        return

    sub_id = int(callback.data.split(":")[1])

    sub_res = await session.execute(
        select(TaskSubmission).where(TaskSubmission.id == sub_id).with_for_update()
    )
    sub = sub_res.scalar_one_or_none()

    if not sub or sub.status != "pending":
        await callback.answer("Вже оброблено.", show_alert=True)
        return

    sub.status      = "approved"
    sub.reviewed_at = datetime.now(tz=timezone.utc)

    # Використовуємо reward_snapshot — суму зафіксовану в момент подачі.
    # Це захищає від зміни суми завдання між подачею та схваленням.
    reward = sub.reward_snapshot

    user_res = await session.execute(
        select(User).where(User.id == sub.user_id).with_for_update()
    )
    db_user = user_res.scalar_one()
    db_user.balance      += reward
    db_user.total_earned += reward

    await session.commit()                                  # ← commit тільки тут

    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        f"✅ #{sub_id} прийнято. Нараховано {reward} UAH юзеру {sub.user_id}."
    )
    try:
        await callback.message.bot.send_message(
            sub.user_id,
            f"✅ <b>Завдання схвалено адміністратором!</b>\n\n"
            f"💰 Нараховано <code>{reward} UAH</code> на ваш баланс.",
            parse_mode="HTML",
        )
    except Exception:
        pass


@router.callback_query(F.data.startswith("sub_reject:"))
async def cb_reject(callback: CallbackQuery, session: AsyncSession) -> None:
    if not _is_admin(callback.from_user.id):
        return

    sub_id = int(callback.data.split(":")[1])

    sub_res = await session.execute(
        select(TaskSubmission).where(TaskSubmission.id == sub_id).with_for_update()
    )
    sub = sub_res.scalar_one_or_none()

    if not sub or sub.status != "pending":
        await callback.answer("Вже оброблено.", show_alert=True)
        return

    sub.status        = "rejected"
    sub.reviewed_at   = datetime.now(tz=timezone.utc)
    sub.reject_reason = "Відхилено адміністратором"

    await session.commit()                                  # ← commit

    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer("❌ Відхилено.")
    try:
        await callback.message.bot.send_message(
            sub.user_id,
            "❌ <b>Завдання відхилено.</b>\n\n"
            "Якщо вважаєте це помилкою — зверніться до підтримки.",
            parse_mode="HTML",
        )
    except Exception:
        pass


# ─────────────────────────────────────────────
# /broadcast — масова розсилка
# ─────────────────────────────────────────────
@router.message(Command("broadcast"))
async def cmd_broadcast(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id):
        return
    await state.set_state(AdminBroadcastFlow.enter_text)
    await message.answer("📢 Введіть текст розсилки (HTML підтримується):")


@router.message(AdminBroadcastFlow.enter_text)
async def broadcast_send(message: Message, session: AsyncSession, state: FSMContext) -> None:
    # ← ВИПРАВЛЕНО: обов'язкова перевірка адміна
    if not _is_admin(message.from_user.id):
        await state.clear()
        return

    await state.clear()
    result   = await session.execute(select(User.id).where(User.is_banned == False))
    user_ids = result.scalars().all()

    sent = failed = 0
    for uid in user_ids:
        try:
            await message.bot.send_message(uid, message.text, parse_mode="HTML")
            sent += 1
        except Exception:
            failed += 1

    await message.answer(
        f"📢 Розсилка завершена.\n✅ Доставлено: {sent}\n❌ Помилок: {failed}"
    )
