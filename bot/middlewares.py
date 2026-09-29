from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from bot.db import Database


class RememberUsers(BaseMiddleware):
    """Запам'ятовує id і @username тих, хто пише боту в особисті.

    Бот може написати людині лише за id і лише якщо вона хоч раз писала боту, —
    так відповідальні за служіння отримують відгуки особисто.
    """

    def __init__(self, db: Database) -> None:
        self.db = db
        self._seen: dict[int, tuple[str | None, str]] = {}  # щоб не писати в базу на кожне повідомлення

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if isinstance(event, Message):
            chat = event.chat
        elif isinstance(event, CallbackQuery) and event.message:
            chat = event.message.chat
        else:
            chat = None
        user = event.from_user
        if chat and chat.type == "private" and user:
            info = (user.username, user.full_name)
            if self._seen.get(user.id) != info:
                await self.db.upsert_user(user.id, user.username, user.full_name)
                self._seen[user.id] = info
        return await handler(event, data)
