from aiogram.filters.callback_data import CallbackData
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.sections import MENU_SECTIONS, SECTIONS


class Nav(CallbackData, prefix="nav"):
    section: str  # ключ розділу або "menu"


class FormCb(CallbackData, prefix="form"):
    action: str  # start | skip | send | restart | cancel


BACK_BUTTON = InlineKeyboardButton(text="⬅️ Меню", callback_data=Nav(section="menu").pack())


def main_menu_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for key in MENU_SECTIONS:
        kb.button(text=SECTIONS[key].title, callback_data=Nav(section=key))
    kb.adjust(2)
    return kb.as_markup()


def back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[BACK_BUTTON]])


def meet_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📝 Заповнити анкету", callback_data=FormCb(action="start").pack())],
            [BACK_BUTTON],
        ]
    )


def form_cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="❌ Скасувати", callback_data=FormCb(action="cancel").pack())]]
    )


def form_skip_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Пропустити ➡️", callback_data=FormCb(action="skip").pack())],
            [InlineKeyboardButton(text="❌ Скасувати", callback_data=FormCb(action="cancel").pack())],
        ]
    )


def form_confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Надіслати", callback_data=FormCb(action="send").pack())],
            [
                InlineKeyboardButton(text="✏️ Заново", callback_data=FormCb(action="restart").pack()),
                InlineKeyboardButton(text="❌ Скасувати", callback_data=FormCb(action="cancel").pack()),
            ],
        ]
    )


SKIP_PHONE_TEXT = "Пропустити"


def phone_kb() -> ReplyKeyboardMarkup:
    # request_contact можливий лише у reply-клавіатурі
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📱 Поділитися номером", request_contact=True)],
            [KeyboardButton(text=SKIP_PHONE_TEXT)],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
