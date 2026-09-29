from aiogram import F, Router
from aiogram.filters import CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot.db import Database
from bot.keyboards import MENU_BUTTONS, main_menu_kb, meet_kb
from bot.render import send_section

router = Router(name="user")
router.message.filter(F.chat.type == "private")


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, db: Database) -> None:
    await state.clear()
    await send_section(message.bot, message.chat.id, db, "welcome", main_menu_kb())


# Натискання кнопки розділу працює і посеред анкети — тоді анкета скасовується
@router.message(F.text.in_(MENU_BUTTONS))
async def on_section(message: Message, state: FSMContext, db: Database) -> None:
    await state.clear()
    key = MENU_BUTTONS[message.text]
    markup = meet_kb() if key == "meet" else main_menu_kb()
    await send_section(message.bot, message.chat.id, db, key, markup)


@router.message(StateFilter(None))
async def fallback(message: Message, db: Database) -> None:
    await send_section(message.bot, message.chat.id, db, "welcome", main_menu_kb())
