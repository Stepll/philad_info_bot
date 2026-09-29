from contextlib import suppress

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.db import Database
from bot.keyboards import Nav, back_kb, main_menu_kb, meet_kb
from bot.render import send_section
from bot.sections import SECTIONS

router = Router(name="user")
router.message.filter(F.chat.type == "private")


@router.message(CommandStart())
@router.message(Command("menu"))
async def cmd_start(message: Message, state: FSMContext, db: Database) -> None:
    await state.clear()
    await send_section(message.bot, message.chat.id, db, "welcome", main_menu_kb())


@router.callback_query(Nav.filter())
async def on_nav(callback: CallbackQuery, callback_data: Nav, state: FSMContext, db: Database) -> None:
    await callback.answer()
    key = callback_data.section

    # Прибираємо попереднє повідомлення, щоб чат не засмічувався
    with suppress(TelegramBadRequest):
        await callback.message.delete()

    if key == "menu" or key not in SECTIONS:
        await state.clear()
        await send_section(callback.bot, callback.message.chat.id, db, "welcome", main_menu_kb())
        return

    markup = meet_kb() if key == "meet" else back_kb()
    await send_section(callback.bot, callback.message.chat.id, db, key, markup)


@router.message(StateFilter(None))
async def fallback(message: Message, db: Database) -> None:
    await send_section(message.bot, message.chat.id, db, "welcome", main_menu_kb())
