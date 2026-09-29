"""Посилання на сторінку події для кнопки «Додати в календар».

Telegram не повідомляє боту про натискання кнопки-посилання, тому посилання несе
підписаний параметр ?m=<chat>.<message>.<підпис>: відкривши сторінку, сервер знає,
хто і з якого постера її відкрив, — позначає «✅ У календарі» і оновлює кнопку.
Підпис (ключ — від токена бота) не дає підробити чужий chat/message.
"""

import hashlib
import hmac

from bot.config import Config

CAL_PATH = "/cal"


def event_page_url(config: Config, event_id: int) -> str:
    return f"{config.public_url}{CAL_PATH}/{event_id}"


def _sign(config: Config, event_id: int, chat_id: int, message_id: int) -> str:
    key = hashlib.sha256(f"cal-link:{config.bot_token}".encode()).digest()
    return hmac.new(key, f"{event_id}.{chat_id}.{message_id}".encode(), hashlib.sha256).hexdigest()[:16]


def carousel_calendar_url(config: Config, event_id: int, chat_id: int, message_id: int) -> str:
    token = f"{chat_id}.{message_id}.{_sign(config, event_id, chat_id, message_id)}"
    return f"{event_page_url(config, event_id)}?m={token}"


def parse_token(config: Config, event_id: int, token: str) -> tuple[int, int] | None:
    """(chat_id, message_id) з параметра ?m=, або None, якщо підпис невірний."""
    try:
        chat, message, sig = token.split(".")
        chat_id, message_id = int(chat), int(message)
    except ValueError:
        return None
    if not hmac.compare_digest(sig, _sign(config, event_id, chat_id, message_id)):
        return None
    return chat_id, message_id
