from aiogram import F, Router
from aiogram.types import (
    CallbackQuery,
    LabeledPrice,
    Message,
    PreCheckoutQuery,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.vip import vip_payment_kb, vip_plans_kb
from config import VIP_PLANS
from database.models import Task, User
from services.vip_service import activate_vip

router = Router()


# ──────────────────────────────────────────────────────────
# 1. ВХІД У РОЗДІЛ
# ──────────────────────────────────────────────────────────
@router.message(F.text == "⭐ VIP Завдання")
async def vip_section(message: Message, user: User, session: AsyncSession) -> None:
    if user.is_vip:
        await _show_vip_tasks(message, user, session)
    else:
        await _show_locked(message)


async def _show_locked(message: Message) -> None:
    await message.answer(
        "⭐ <b>VIP Завдання</b>\n\n"
        "🔒 Розділ доступний лише для <b>VIP-учасників</b>.\n\n"
        "<b>Переваги VIP:</b>\n"
        "• Завдання з підвищеною винагородою\n"
        "• Ексклюзивні партнерські оффери\n"
        "• Пріоритетне підтвердження виконань\n\n"
        "<blockquote>Оберіть тариф для активації 👇</blockquote>",
        reply_markup=vip_plans_kb(),
        parse_mode="HTML",
    )


async def _show_vip_tasks(message: Message, user: User, session: AsyncSession) -> None:
    result = await session.execute(
        select(Task).where(Task.is_vip_only == True, Task.is_active == True)
    )
    tasks = result.scalars().all()

    expires_str = user.vip_expires_at.strftime("%d.%m.%Y %H:%M")
    lines = [f"⭐ <b>VIP Завдання</b>\n<i>Статус активний до {expires_str} UTC</i>\n"]

    if not tasks:
        lines.append("🕐 Наразі немає активних VIP-завдань. Заходьте пізніше.")
    else:
        for t in tasks:
            lines.append(
                f"💎 <b>{t.title}</b>\n"
                f"📝 {t.description}\n"
                f"💰 Винагорода: <code>{t.reward} UAH</code>\n"
            )

    await message.answer("\n".join(lines), parse_mode="HTML")


# ──────────────────────────────────────────────────────────
# 2. ВИБІР ТАРИФУ
# ──────────────────────────────────────────────────────────
@router.callback_query(F.data == "vip_plans")
async def cb_vip_plans(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        "⭐ <b>Оберіть тариф VIP:</b>",
        reply_markup=vip_plans_kb(),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("vip_buy:"))
async def cb_vip_buy(callback: CallbackQuery) -> None:
    days = int(callback.data.split(":")[1])
    plan = VIP_PLANS[days]
    await callback.message.edit_text(
        f"⭐ <b>VIP — {plan['label']}</b>\n\n"
        f"💳 З балансу: <code>{plan['uah']:.0f} UAH</code>\n"
        f"⭐ Telegram Stars: <code>{plan['stars']} Stars</code>\n\n"
        "Оберіть спосіб оплати:",
        reply_markup=vip_payment_kb(days),
        parse_mode="HTML",
    )


# ──────────────────────────────────────────────────────────
# 3. ОПЛАТА З БАЛАНСУ
# ──────────────────────────────────────────────────────────
@router.callback_query(F.data.startswith("vip_pay_balance:"))
async def cb_pay_balance(callback: CallbackQuery, user: User, session: AsyncSession) -> None:
    days = int(callback.data.split(":")[1])
    try:
        sub = await activate_vip(session, user.id, days, payment_method="balance")
        await session.commit()          # ← commit тут, не в сервісі
        expires_str = sub.expires_at.strftime("%d.%m.%Y %H:%M")
        await callback.message.edit_text(
            f"✅ <b>VIP активовано!</b>\n\n"
            f"⭐ Статус дійсний до <b>{expires_str} UTC</b>\n"
            "Переходьте до розділу ⭐ VIP Завдання.",
            parse_mode="HTML",
        )
    except ValueError:
        await session.rollback()        # ← скидаємо FOR UPDATE lock
        await callback.answer(
            "❌ Недостатньо балансу! Поповніть рахунок або оплатіть Stars.",
            show_alert=True,
        )


# ──────────────────────────────────────────────────────────
# 4. ОПЛАТА TELEGRAM STARS
# ──────────────────────────────────────────────────────────
@router.callback_query(F.data.startswith("vip_pay_stars:"))
async def cb_pay_stars(callback: CallbackQuery, user: User) -> None:
    days = int(callback.data.split(":")[1])
    plan = VIP_PLANS[days]
    await callback.message.bot.send_invoice(
        chat_id=callback.from_user.id,
        title=f"⭐ VIP-підписка — {plan['label']}",
        description="Доступ до VIP-завдань із підвищеною винагородою",
        payload=f"vip:{user.id}:{days}",
        currency="XTR",
        prices=[LabeledPrice(label=f"VIP {plan['label']}", amount=plan["stars"])],
    )
    await callback.answer()


@router.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery) -> None:
    await query.answer(ok=True)


@router.message(F.successful_payment)
async def on_successful_payment(message: Message, session: AsyncSession) -> None:
    payload = message.successful_payment.invoice_payload   # "vip:USER_ID:DAYS"
    _, user_id_str, days_str = payload.split(":")
    stars = message.successful_payment.total_amount

    sub = await activate_vip(
        session,
        user_id=int(user_id_str),
        days=int(days_str),
        payment_method="stars",
        stars_paid=stars,
    )
    await session.commit()                                  # ← commit тут
    expires_str = sub.expires_at.strftime("%d.%m.%Y %H:%M")
    await message.answer(
        f"✅ <b>Оплату підтверджено!</b>\n\n"
        f"⭐ VIP активовано до <b>{expires_str} UTC</b>.\n"
        "Переходьте до розділу ⭐ VIP Завдання.",
        parse_mode="HTML",
    )
