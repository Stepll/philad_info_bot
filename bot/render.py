import asyncio

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import BufferedInputFile, InlineKeyboardMarkup, ReplyKeyboardMarkup

from bot.db import Database
from bot.schedule_image import render_schedule
from bot.settings import SCHEDULE_FILE_ID

Markup = InlineKeyboardMarkup | ReplyKeyboardMarkup | None

CAPTION_LIMIT = 1024
# Якщо в розділі немає ні фото, ні тексту — щоб повідомлення не було порожнім
EMPTY_TEXT = "Інформація незабаром з'явиться 🙏"


async def send_section(
    bot: Bot,
    chat_id: int,
    db: Database,
    key: str,
    markup: Markup = None,
) -> None:
    """Надсилає розділ: фото з підписом, або фото + окремий текст, якщо текст задовгий."""
    content = await db.get_section(key)

    if not content.photo_id:
        await bot.send_message(chat_id, content.text or EMPTY_TEXT, reply_markup=markup)
    elif len(content.text) <= CAPTION_LIMIT:
        await bot.send_photo(chat_id, content.photo_id, caption=content.text or None, reply_markup=markup)
    else:
        await bot.send_photo(chat_id, content.photo_id)
        await bot.send_message(chat_id, content.text, reply_markup=markup)


async def invalidate_schedule(db: Database) -> None:
    await db.set_setting(SCHEDULE_FILE_ID, None, 0)


async def send_schedule(bot: Bot, chat_id: int, db: Database, markup: Markup = None) -> None:
    """Надсилає картинку розкладу. Генерує її лише після змін, інакше — з кешу Telegram (file_id)."""
    file_id = await db.get_setting(SCHEDULE_FILE_ID)
    if file_id:
        try:
            await bot.send_photo(chat_id, file_id, reply_markup=markup)
            return
        except TelegramBadRequest:
            pass  # file_id застарів — згенеруємо заново

    items = await db.list_schedule()
    if not items:
        await bot.send_message(chat_id, EMPTY_TEXT, reply_markup=markup)
        return

    image = await asyncio.to_thread(render_schedule, items)
    msg = await bot.send_photo(
        chat_id, BufferedInputFile(image, filename="schedule.jpg"), reply_markup=markup
    )
    await db.set_setting(SCHEDULE_FILE_ID, msg.photo[-1].file_id, 0)
