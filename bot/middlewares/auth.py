from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.engine import async_session_factory
from database.models import User


class AuthMiddleware(BaseMiddleware):
    """
    Виконується перед кожним апдейтом:
      1. Знаходить або створює User у БД.
      2. Оновлює username якщо змінився.
      3. Блокує banned-юзерів.
      4. Кладе user + session у data[].
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        tg_user = data.get("event_from_user")
        if not tg_user:
            return await handler(event, data)

        async with async_session_factory() as session:
            result = await session.execute(
                select(User).where(User.id == tg_user.id)
            )
            user = result.scalar_one_or_none()

            if not user:
                user = User(
                    id=tg_user.id,
                    username=tg_user.username,
                    first_name=tg_user.first_name or "User",
                )
                session.add(user)
                await session.commit()
                await session.refresh(user)
            else:
                if user.username != tg_user.username:
                    user.username = tg_user.username
                    await session.commit()

            if user.is_banned:
                if isinstance(event, Message):
                    await event.answer("🚫 Ваш акаунт заблоковано.")
                return

            data["user"] = user
            data["session"] = session
            return await handler(event, data)
