from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from bot.db import Database
from bot.keyboards import MENU_BUTTONS, main_menu_kb, url_button_kb
from bot.render import send_schedule, send_section
from bot.sections import SECTIONS
from bot.settings import LINK_SECTIONS, SECTION_URL_BUTTONS, SECTION_URL_KEYS

router = Router(name="user")
router.message.filter(F.chat.type == "private")


@router.message(CommandStart())
async def cmd_start(message: Message, db: Database) -> None:
    await send_section(message.bot, message.chat.id, db, "welcome", main_menu_kb())


# Лише кнопка-посилання («Давай знайомитись», «Потреби»)
LINK_SECTION_TITLES = {SECTIONS[key].title: key for key in LINK_SECTIONS}


@router.message(F.text.in_(LINK_SECTION_TITLES))
async def on_link_section(message: Message, db: Database) -> None:
    key = LINK_SECTION_TITLES[message.text]
    text, button, missing = LINK_SECTIONS[key]
    url = await db.get_setting(SECTION_URL_KEYS[key])
    if url:
        await message.answer(text, reply_markup=url_button_kb(button, url))
    else:
        await message.answer(missing, reply_markup=main_menu_kb())


@router.message(F.text == SECTIONS["schedule"].title)
async def on_schedule(message: Message, db: Database) -> None:
    await send_schedule(message.bot, message.chat.id, db, main_menu_kb())


# Фото + текст + кнопка з посиланням (пожертви, домашні групи…)
URL_SECTION_TITLES = {SECTIONS[key].title: key for key in SECTION_URL_BUTTONS}


@router.message(F.text.in_(URL_SECTION_TITLES))
async def on_url_section(message: Message, db: Database) -> None:
    key = URL_SECTION_TITLES[message.text]
    url = await db.get_setting(SECTION_URL_KEYS[key])
    markup = url_button_kb(SECTION_URL_BUTTONS[key], url) if url else main_menu_kb()
    await send_section(message.bot, message.chat.id, db, key, markup)


@router.message(F.text.in_(MENU_BUTTONS))
async def on_section(message: Message, db: Database) -> None:
    await send_section(message.bot, message.chat.id, db, MENU_BUTTONS[message.text], main_menu_kb())


@router.message()
async def fallback(message: Message, db: Database) -> None:
    await send_section(message.bot, message.chat.id, db, "welcome", main_menu_kb())
