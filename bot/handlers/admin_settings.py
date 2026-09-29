"""Інтерактивне меню /settings у групі адмінів."""

from contextlib import suppress
from html import escape
from urllib.parse import urlparse

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.db import Database
from bot.sections import MENU_SECTIONS, SECTIONS
from bot.settings import MEET_FORM_URL


class SettingsCb(CallbackData, prefix="st"):
    action: str  # list | open | edit_url | cancel_input
    section: str = ""


class SettingsInput(StatesGroup):
    meet_url = State()


# --- Екрани ------------------------------------------------------------------


def _list_screen() -> tuple[str, InlineKeyboardMarkup]:
    kb = InlineKeyboardBuilder()
    for key in MENU_SECTIONS:
        kb.button(text=SECTIONS[key].title, callback_data=SettingsCb(action="open", section=key))
    kb.adjust(2)
    return "⚙️ <b>Налаштування</b>\n\nОберіть розділ:", kb.as_markup()


def _back_button(kb: InlineKeyboardBuilder) -> None:
    kb.button(text="⬅️ Назад", callback_data=SettingsCb(action="list"))


async def _section_screen(db: Database, key: str, note: str = "") -> tuple[str, InlineKeyboardMarkup]:
    kb = InlineKeyboardBuilder()
    title = f"⚙️ <b>{SECTIONS[key].title}</b>\n\n"

    if key == "meet":
        url = await db.get_setting(MEET_FORM_URL)
        current = escape(url) if url else "<i>не задано</i>"
        text = f"{title}Поточне посилання на форму: {current}"
        kb.button(text="✏️ Змінити посилання", callback_data=SettingsCb(action="edit_url", section=key))
    else:
        text = f"{title}Налаштувань для цього розділу поки немає."

    _back_button(kb)
    kb.adjust(1)
    if note:
        text = f"{note}\n\n{text}"
    return text, kb.as_markup()


def _url_prompt_screen(error: str = "") -> tuple[str, InlineKeyboardMarkup]:
    kb = InlineKeyboardBuilder()
    kb.button(text="⬅️ Назад", callback_data=SettingsCb(action="cancel_input", section="meet"))
    text = "✏️ Надішліть повідомлення з посиланням на Google Form."
    if error:
        text = f"⚠️ {error}\n\n{text}"
    return text, kb.as_markup()


async def _edit(bot: Bot, chat_id: int, message_id: int, screen: tuple[str, InlineKeyboardMarkup]) -> None:
    text, markup = screen
    # "message is not modified" та подібне — не критично
    with suppress(TelegramBadRequest):
        await bot.edit_message_text(
            text, chat_id=chat_id, message_id=message_id, reply_markup=markup,
            disable_web_page_preview=True,
        )


def _is_valid_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in ("http", "https") and bool(parsed.netloc) and " " not in value


# --- Роутер ------------------------------------------------------------------


def create_router(admin_chat_id: int) -> Router:
    router = Router(name="admin_settings")
    router.message.filter(F.chat.id == admin_chat_id)
    router.callback_query.filter(F.message.chat.id == admin_chat_id)

    @router.message(Command("settings"))
    async def cmd_settings(message: Message, state: FSMContext) -> None:
        await state.clear()
        text, markup = _list_screen()
        await message.answer(text, reply_markup=markup)

    @router.callback_query(SettingsCb.filter(F.action == "list"))
    async def on_list(callback: CallbackQuery, state: FSMContext) -> None:
        await callback.answer()
        await state.clear()
        await _edit(callback.bot, callback.message.chat.id, callback.message.message_id, _list_screen())

    @router.callback_query(SettingsCb.filter(F.action.in_({"open", "cancel_input"})))
    async def on_open(callback: CallbackQuery, callback_data: SettingsCb, state: FSMContext, db: Database) -> None:
        await callback.answer()
        await state.clear()
        screen = await _section_screen(db, callback_data.section)
        await _edit(callback.bot, callback.message.chat.id, callback.message.message_id, screen)

    @router.callback_query(SettingsCb.filter(F.action == "edit_url"))
    async def on_edit_url(callback: CallbackQuery, state: FSMContext) -> None:
        await callback.answer()
        await state.set_state(SettingsInput.meet_url)
        await state.update_data(settings_msg_id=callback.message.message_id)
        await _edit(callback.bot, callback.message.chat.id, callback.message.message_id, _url_prompt_screen())

    @router.message(SettingsInput.meet_url)
    async def on_meet_url(message: Message, state: FSMContext, db: Database) -> None:
        data = await state.get_data()
        settings_msg_id = data["settings_msg_id"]
        url = (message.text or "").strip()

        with suppress(TelegramBadRequest):
            await message.delete()

        if not _is_valid_url(url):
            screen = _url_prompt_screen("Це не схоже на посилання. Воно має починатися з https://")
            await _edit(message.bot, message.chat.id, settings_msg_id, screen)
            return

        await db.set_setting(MEET_FORM_URL, url, message.from_user.id)
        await state.clear()
        screen = await _section_screen(db, "meet", note="✅ Посилання збережено.")
        await _edit(message.bot, message.chat.id, settings_msg_id, screen)

    return router
