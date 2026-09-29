from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from aiogram.utils.keyboard import ReplyKeyboardBuilder

from bot.sections import MENU_SECTIONS, SECTIONS

# Текст кнопки -> ключ розділу
MENU_BUTTONS = {SECTIONS[key].title: key for key in MENU_SECTIONS}


def main_menu_kb() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    for title in MENU_BUTTONS:
        kb.button(text=title)
    kb.adjust(2)
    return kb.as_markup(resize_keyboard=True, is_persistent=True)


def meet_form_kb(url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="📝 Заповнити анкету", url=url)]]
    )
