from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup

from bot.db import Database

CAPTION_LIMIT = 1024


async def send_section(
    bot: Bot,
    chat_id: int,
    db: Database,
    key: str,
    markup: InlineKeyboardMarkup | ReplyKeyboardMarkup | None = None,
) -> None:
    """Надсилає розділ: фото з підписом, або фото + окремий текст, якщо текст задовгий."""
    content = await db.get_section(key)

    if not content.photo_id:
        await bot.send_message(chat_id, content.text, reply_markup=markup)
    elif len(content.text) <= CAPTION_LIMIT:
        await bot.send_photo(chat_id, content.photo_id, caption=content.text, reply_markup=markup)
    else:
        await bot.send_photo(chat_id, content.photo_id)
        await bot.send_message(chat_id, content.text, reply_markup=markup)
