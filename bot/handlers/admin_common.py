"""Спільне для меню /settings: callback-дані, редагування екранів і запити на введення."""

from contextlib import suppress
from dataclasses import dataclass, field
from urllib.parse import urlparse

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters.callback_data import CallbackData
from aiogram.types import ForceReply, InlineKeyboardMarkup, Message

Screen = tuple[str, InlineKeyboardMarkup]


class SettingsCb(CallbackData, prefix="st"):
    action: str  # list | open | edit | delete | cancel_input
    section: str = ""
    field: str = ""  # photo | text | url


class ScheduleCb(CallbackData, prefix="sc"):
    # list | item | add | add_day | day | set_day | time | title | color | set_color
    # | delete | delete_yes | preview | cancel_input
    action: str
    item: int = 0
    value: str = ""


class EventCb(CallbackData, prefix="ev"):
    # list | open | add | edit | clear | delete | delete_yes | preview | cancel_input
    action: str
    event: int = 0
    value: str = ""  # поле: poster | text | date | time | place | url


class ServingCb(CallbackData, prefix="sv"):
    # list | open | add | edit | clear | skip | preview | delete | delete_yes | cancel_input
    action: str
    need: int = 0
    value: str = ""  # поле: title | summary | description | responsible


def is_valid_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in ("http", "https") and bool(parsed.netloc) and " " not in value


async def edit_screen(bot: Bot, chat_id: int, message_id: int, screen: Screen) -> None:
    text, markup = screen
    # "message is not modified" та подібне — не критично
    with suppress(TelegramBadRequest):
        await bot.edit_message_text(
            text, chat_id=chat_id, message_id=message_id, reply_markup=markup,
            disable_web_page_preview=True,
        )


@dataclass
class PendingInput:
    """Бот чекає від адміна значення у відповідь на повідомлення-запит."""

    kind: str  # хто обробляє: "section" | "schedule" | "event" | "serving"
    settings_msg_id: int
    prompt_msg_id: int
    user_id: int
    data: dict = field(default_factory=dict)


class Prompts:
    """Очікуване введення, по одному на чат.

    Приймаємо відповідь (reply) на запит — такі повідомлення доходять до бота навіть
    з увімкненим privacy mode і від анонімних адмінів.
    """

    def __init__(self) -> None:
        self._pending: dict[int, PendingInput] = {}

    async def drop(self, bot: Bot, chat_id: int) -> PendingInput | None:
        p = self._pending.pop(chat_id, None)
        if p:
            with suppress(TelegramBadRequest):
                await bot.delete_message(chat_id, p.prompt_msg_id)
        return p

    async def ask(
        self,
        bot: Bot,
        chat_id: int,
        text: str,
        *,
        kind: str,
        settings_msg_id: int,
        user_id: int,
        data: dict,
        placeholder: str | None = None,
        error: str = "",
    ) -> None:
        await self.drop(bot, chat_id)
        if error:
            text = f"⚠️ {error}\n\n{text}"
        prompt = await bot.send_message(
            chat_id, text, reply_markup=ForceReply(input_field_placeholder=placeholder)
        )
        self._pending[chat_id] = PendingInput(kind, settings_msg_id, prompt.message_id, user_id, data)

    def filter(self, kind: str):
        def check(message: Message) -> bool:
            p = self._pending.get(message.chat.id)
            if not p or p.kind != kind:
                return False
            reply = message.reply_to_message
            return (reply is not None and reply.message_id == p.prompt_msg_id) or (
                message.from_user is not None and message.from_user.id == p.user_id
            )

        return check


prompts = Prompts()
