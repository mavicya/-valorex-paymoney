"""
Withdrawals handler — FSM вивід коштів.

ТРАНЗАКЦІЇ: session.begin() НЕ використовується.
commit() викликається після всіх змін у кінці handler.
"""
from decimal import Decimal

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.states import WithdrawFlow
from database.models import User, Withdrawal

router = Router()

MIN_WITHDRAWAL = Decimal("50")

CURRENCIES: dict[str, str] = {
    "uah":   "💳 Гривні (UAH)",
    "rub":   "💳 Рублі (RUB)",
    "usdt":  "💎 USDT TRC20",
    "ton":   "💎 TON",
    "stars": "⭐ Telegram Stars",
}


# ─────────────────────────────────────────────
# СТАРТ
# ─────────────────────────────────────────────
@router.callback_query(F.data == "withdraw_start")
async def cb_withdraw_start(callback: CallbackQuery, state: FSMContext) -> None:
    buttons = [
        [InlineKeyboardButton(text=label, callback_data=f"wd_cur:{key}")]
        for key, label in CURRENCIES.items()
    ]
    buttons.append([InlineKeyboardButton(text="❌ Скасувати", callback_data="wd_cancel")])

    await callback.message.edit_text(
        "💳 <b>Вивід коштів</b>\n\nОберіть спосіб виплати:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
    )
    await state.set_state(WithdrawFlow.select_currency)


# ─────────────────────────────────────────────
# ВИБІР ВАЛЮТИ
# ─────────────────────────────────────────────
@router.callback_query(F.data.startswith("wd_cur:"), WithdrawFlow.select_currency)
async def cb_select_currency(callback: CallbackQuery, state: FSMContext) -> None:
    currency = callback.data.split(":")[1]
    await state.update_data(currency=currency)
    await state.set_state(WithdrawFlow.enter_requisites)

    await callback.message.edit_text(
        f"💳 Вивід через <b>{CURRENCIES[currency]}</b>\n\n"
        "Введіть реквізити:\n"
        "<i>(номер картки, адреса гаманця або інше)</i>",
        parse_mode="HTML",
    )


# ─────────────────────────────────────────────
# РЕКВІЗИТИ
# ─────────────────────────────────────────────
@router.message(WithdrawFlow.enter_requisites)
async def enter_requisites(message: Message, state: FSMContext) -> None:
    await state.update_data(requisites=message.text.strip())
    await state.set_state(WithdrawFlow.enter_amount)
    await message.answer(
        f"💰 Введіть суму для виводу.\n<i>Мінімум: {MIN_WITHDRAWAL} UAH</i>",
        parse_mode="HTML",
    )


# ─────────────────────────────────────────────
# СУМА
# ─────────────────────────────────────────────
@router.message(WithdrawFlow.enter_amount)
async def enter_amount(message: Message, user: User, state: FSMContext) -> None:
    try:
        amount = Decimal(message.text.replace(",", "."))
        assert amount > 0
    except Exception:
        await message.answer(
            "❌ Введіть коректну суму числом, наприклад: <code>150</code>",
            parse_mode="HTML",
        )
        return

    if amount < MIN_WITHDRAWAL:
        await message.answer(
            f"❌ Мінімальна сума: <code>{MIN_WITHDRAWAL} UAH</code>",
            parse_mode="HTML",
        )
        return

    if amount > user.balance:
        await message.answer(
            f"❌ Недостатньо коштів.\n💰 Ваш баланс: <code>{user.balance:.2f} UAH</code>",
            parse_mode="HTML",
        )
        return

    await state.update_data(amount=str(amount))
    data = await state.get_data()
    await state.set_state(WithdrawFlow.confirm)

    await message.answer(
        f"📋 <b>Підтвердження виводу</b>\n\n"
        f"💰 Сума: <code>{amount:.2f} UAH</code>\n"
        f"💳 Спосіб: {CURRENCIES[data['currency']]}\n"
        f"📝 Реквізити: <code>{data['requisites']}</code>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Підтвердити", callback_data="wd_confirm")],
            [InlineKeyboardButton(text="❌ Скасувати",   callback_data="wd_cancel")],
        ]),
        parse_mode="HTML",
    )


# ─────────────────────────────────────────────
# ПІДТВЕРДЖЕННЯ (ACID без begin())
# ─────────────────────────────────────────────
@router.callback_query(F.data == "wd_confirm", WithdrawFlow.confirm)
async def cb_confirm(
    callback: CallbackQuery,
    user: User,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    data   = await state.get_data()
    amount = Decimal(data["amount"])

    # SELECT з FOR UPDATE — блокує рядок юзера в рамках autobegin-транзакції
    result  = await session.execute(
        select(User).where(User.id == user.id).with_for_update()
    )
    db_user = result.scalar_one()

    if db_user.balance < amount:
        # Не робимо rollback явно — autobegin закриється middleware; FOR UPDATE відпуститься
        await callback.answer("❌ Баланс змінився. Спробуйте знову.", show_alert=True)
        await state.clear()
        return

    db_user.balance -= amount

    w = Withdrawal(
        user_id=user.id,
        amount=amount,
        currency=data["currency"],
        requisites=data["requisites"],
        status="pending",
    )
    session.add(w)
    await session.commit()                                  # ← commit

    await state.clear()
    await callback.message.edit_text(
        f"✅ <b>Заявку на вивід прийнято!</b>\n\n"
        f"💰 Сума: <code>{amount:.2f} UAH</code>\n"
        "Адміністратор обробить запит найближчим часом.",
        parse_mode="HTML",
    )

    from config import settings
    for admin_id in settings.ADMIN_IDS:
        try:
            await callback.message.bot.send_message(
                admin_id,
                f"💳 <b>Новий запит на вивід!</b>\n\n"
                f"👤 @{user.username or '—'} (<code>{user.id}</code>)\n"
                f"💰 {amount:.2f} UAH → {CURRENCIES[data['currency']]}\n"
                f"📝 {data['requisites']}",
                parse_mode="HTML",
            )
        except Exception:
            pass


# ─────────────────────────────────────────────
# СКАСУВАННЯ
# ─────────────────────────────────────────────
@router.callback_query(F.data == "wd_cancel")
async def cb_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("❌ Вивід скасовано.")
