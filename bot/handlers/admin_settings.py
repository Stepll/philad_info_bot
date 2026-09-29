"""Інтерактивне меню /settings у групі адмінів."""

from contextlib import suppress
from dataclasses import dataclass
from html import escape
from urllib.parse import urlparse

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.filters.callback_data import CallbackData
from aiogram.types import CallbackQuery, ForceReply, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.db import Database
from bot.sections import MENU_SECTIONS, SECTIONS
from bot.settings import MEET_FORM_URL


class SettingsCb(CallbackData, prefix="st"):
    action: str  # list | open | edit_url | cancel_input
    section: str = ""


@dataclass
class PendingInput:
    """Бот чекає від адміна посилання у відповідь на повідомлення-запит."""

    settings_msg_id: int
    prompt_msg_id: int
    user_id: int


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


def _waiting_screen() -> tuple[str, InlineKeyboardMarkup]:
    kb = InlineKeyboardBuilder()
    kb.button(text="⬅️ Назад", callback_data=SettingsCb(action="cancel_input", section="meet"))
    return "⚙️ <b>🤝 Давай знайомитись</b>\n\n✏️ Очікую нове посилання на форму…", kb.as_markup()


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

    # Очікуване введення (на чат). Приймаємо відповідь (reply) на запит — такі повідомлення
    # доходять до бота навіть з увімкненим privacy mode і від анонімних адмінів.
    pending: dict[int, PendingInput] = {}

    async def drop_pending(bot: Bot, chat_id: int) -> PendingInput | None:
        p = pending.pop(chat_id, None)
        if p:
            with suppress(TelegramBadRequest):
                await bot.delete_message(chat_id, p.prompt_msg_id)
        return p

    async def ask_url(bot: Bot, chat_id: int, settings_msg_id: int, user_id: int, error: str = "") -> None:
        text = "✏️ Надішліть у відповідь на це повідомлення посилання на Google Form."
        if error:
            text = f"⚠️ {error}\n\n{text}"
        prompt = await bot.send_message(
            chat_id, text,
            reply_markup=ForceReply(input_field_placeholder="https://forms.gle/..."),
        )
        pending[chat_id] = PendingInput(settings_msg_id, prompt.message_id, user_id)

    def is_pending_input(message: Message) -> bool:
        p = pending.get(message.chat.id)
        if not p:
            return False
        reply = message.reply_to_message
        return (reply is not None and reply.message_id == p.prompt_msg_id) or (
            message.from_user is not None and message.from_user.id == p.user_id
        )

    @router.message(Command("settings"))
    async def cmd_settings(message: Message) -> None:
        await drop_pending(message.bot, message.chat.id)
        text, markup = _list_screen()
        await message.answer(text, reply_markup=markup)

    @router.callback_query(SettingsCb.filter(F.action == "list"))
    async def on_list(callback: CallbackQuery) -> None:
        await callback.answer()
        await _edit(callback.bot, callback.message.chat.id, callback.message.message_id, _list_screen())

    @router.callback_query(SettingsCb.filter(F.action.in_({"open", "cancel_input"})))
    async def on_open(callback: CallbackQuery, callback_data: SettingsCb, db: Database) -> None:
        await callback.answer()
        await drop_pending(callback.bot, callback.message.chat.id)
        screen = await _section_screen(db, callback_data.section)
        await _edit(callback.bot, callback.message.chat.id, callback.message.message_id, screen)

    @router.callback_query(SettingsCb.filter(F.action == "edit_url"))
    async def on_edit_url(callback: CallbackQuery) -> None:
        await callback.answer()
        chat_id = callback.message.chat.id
        await drop_pending(callback.bot, chat_id)
        await _edit(callback.bot, chat_id, callback.message.message_id, _waiting_screen())
        await ask_url(callback.bot, chat_id, callback.message.message_id, callback.from_user.id)

    @router.message(is_pending_input)
    async def on_meet_url(message: Message, db: Database) -> None:
        p = await drop_pending(message.bot, message.chat.id)
        url = (message.text or "").strip()

        with suppress(TelegramBadRequest):
            await message.delete()

        if not _is_valid_url(url):
            await ask_url(
                message.bot, message.chat.id, p.settings_msg_id, p.user_id,
                error="Це не схоже на посилання. Воно має починатися з https://",
            )
            return

        await db.set_setting(MEET_FORM_URL, url, message.from_user.id)
        screen = await _section_screen(db, "meet", note="✅ Посилання збережено.")
        await _edit(message.bot, message.chat.id, p.settings_msg_id, screen)

    return router
