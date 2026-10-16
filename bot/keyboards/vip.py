from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from config import VIP_PLANS


def vip_plans_kb() -> InlineKeyboardMarkup:
    """Вибір тарифного плану VIP."""
    rows = [
        [InlineKeyboardButton(
            text=f"⭐ {plan['label']} — {plan['uah']:.0f} UAH / {plan['stars']} Stars",
            callback_data=f"vip_buy:{days}",
        )]
        for days, plan in VIP_PLANS.items()
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def vip_payment_kb(days: int) -> InlineKeyboardMarkup:
    """Вибір способу оплати після вибору тарифу."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 З балансу",       callback_data=f"vip_pay_balance:{days}")],
        [InlineKeyboardButton(text="⭐ Telegram Stars",   callback_data=f"vip_pay_stars:{days}")],
        [InlineKeyboardButton(text="← Назад",            callback_data="vip_plans")],
    ])
