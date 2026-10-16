from aiogram.types import KeyboardButton, ReplyKeyboardMarkup


def main_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📋 Завдання"),     KeyboardButton(text="⭐ VIP Завдання")],
            [KeyboardButton(text="👤 Профіль"),      KeyboardButton(text="🏆 Топ виводів")],
            [KeyboardButton(text="🤝 Співпраця"),    KeyboardButton(text="🛠 Підтримка")],
            [KeyboardButton(text="🛒 Замовникам"),   KeyboardButton(text="💬 Відгуки")],
            [KeyboardButton(text="ℹ️ Про сервіс"),   KeyboardButton(text="📜 Правила")],
        ],
        resize_keyboard=True,
    )
