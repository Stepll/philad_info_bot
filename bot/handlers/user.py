from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from bot.db import Database
from bot.keyboards import MENU_BUTTONS, main_menu_kb, meet_form_kb
from bot.render import send_section
from bot.sections import SECTIONS
from bot.settings import MEET_FORM_URL

router = Router(name="user")
router.message.filter(F.chat.type == "private")


@router.message(CommandStart())
async def cmd_start(message: Message, db: Database) -> None:
    await send_section(message.bot, message.chat.id, db, "welcome", main_menu_kb())


@router.message(F.text == SECTIONS["meet"].title)
async def on_meet(message: Message, db: Database) -> None:
    url = await db.get_setting(MEET_FORM_URL)
    if url:
        await message.answer("Давайте знайомитись! 👇", reply_markup=meet_form_kb(url))
    else:
        await message.answer("Анкета незабаром з'явиться 🙏", reply_markup=main_menu_kb())


@router.message(F.text.in_(MENU_BUTTONS))
async def on_section(message: Message, db: Database) -> None:
    await send_section(message.bot, message.chat.id, db, MENU_BUTTONS[message.text], main_menu_kb())


@router.message()
async def fallback(message: Message, db: Database) -> None:
    await send_section(message.bot, message.chat.id, db, "welcome", main_menu_kb())
