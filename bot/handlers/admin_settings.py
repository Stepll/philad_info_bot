"""Інтерактивне меню /settings у групі адмінів."""

from contextlib import suppress
from html import escape
from urllib.parse import urlparse

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.db import Database
from bot.handlers.admin_common import ScheduleCb, SettingsCb, edit_screen, prompts
from bot.render import CAPTION_LIMIT
from bot.sections import MENU_SECTIONS, SECTIONS
from bot.settings import SECTION_FIELDS, SECTION_URL_KEYS

# Якщо текст розділу довший — у меню показуємо лише його довжину
TEXT_PREVIEW_LIMIT = 2500

FIELD_WAITING = {
    "photo": "🖼 Очікую нове фото…",
    "text": "📝 Очікую новий текст…",
    "url": "🔗 Очікую нове посилання…",
}

FIELD_PROMPT = {
    "photo": "🖼 Надішліть у відповідь на це повідомлення фото.",
    "text": "📝 Надішліть у відповідь на це повідомлення текст. Форматування (жирний, курсив, посилання) збережеться.",
    "url": "🔗 Надішліть у відповідь на це повідомлення посилання.",
}

FIELD_PLACEHOLDER = {"photo": None, "text": "Текст розділу…", "url": "https://..."}

FIELD_DELETED = {"photo": "🗑 Фото видалено.", "text": "🗑 Текст видалено.", "url": "🗑 Посилання видалено."}
FIELD_SAVED = {"photo": "✅ Фото збережено.", "text": "✅ Текст збережено.", "url": "✅ Посилання збережено."}


# --- Екрани ------------------------------------------------------------------


def list_screen() -> tuple[str, InlineKeyboardMarkup]:
    kb = InlineKeyboardBuilder()
    for key in MENU_SECTIONS:
        if key == "schedule":
            kb.button(text=SECTIONS[key].title, callback_data=ScheduleCb(action="list"))
        else:
            kb.button(text=SECTIONS[key].title, callback_data=SettingsCb(action="open", section=key))
    kb.adjust(2)
    return "⚙️ <b>Налаштування</b>\n\nОберіть розділ:", kb.as_markup()


def _header(key: str) -> str:
    return f"⚙️ <b>{SECTIONS[key].title}</b>\n\n"


async def _section_screen(db: Database, key: str, note: str = "") -> tuple[str, InlineKeyboardMarkup]:
    kb = InlineKeyboardBuilder()
    fields = SECTION_FIELDS.get(key, ())
    lines: list[str] = []
    sizes: list[int] = []

    def row(field: str, has_value: bool, edit: str, add: str) -> None:
        kb.button(
            text=edit if has_value else add,
            callback_data=SettingsCb(action="edit", section=key, field=field),
        )
        if has_value:
            kb.button(text="🗑 Видалити", callback_data=SettingsCb(action="delete", section=key, field=field))
        sizes.append(2 if has_value else 1)

    content = await db.get_section(key) if {"photo", "text"} & set(fields) else None

    if "photo" in fields:
        lines.append(f"🖼 <b>Фото:</b> {'є' if content.photo_id else '<i>немає</i>'}")
        row("photo", bool(content.photo_id), "🖼 Змінити фото", "🖼 Додати фото")

    if "url" in fields:
        url = await db.get_setting(SECTION_URL_KEYS[key])
        lines.append(f"🔗 <b>Посилання:</b> {escape(url) if url else '<i>не задано</i>'}")
        row("url", bool(url), "🔗 Змінити посилання", "🔗 Додати посилання")

    if "text" in fields:
        if not content.text:
            preview = "<i>немає</i>"
        elif len(content.text) > TEXT_PREVIEW_LIMIT:
            preview = f"<i>{len(content.text)} символів (перегляд: /show {key})</i>"
        else:
            preview = f"\n{content.text}"
        lines.append(f"📝 <b>Текст:</b> {preview}")
        row("text", bool(content.text), "📝 Змінити текст", "📝 Додати текст")

    if not fields:
        lines.append("Налаштувань для цього розділу поки немає.")

    kb.button(text="⬅️ Назад", callback_data=SettingsCb(action="list"))
    kb.adjust(*sizes, 1)

    text = _header(key) + "\n\n".join(lines)
    if note:
        text = f"{note}\n\n{text}"
    return text, kb.as_markup()


def _waiting_screen(key: str, field: str) -> tuple[str, InlineKeyboardMarkup]:
    kb = InlineKeyboardBuilder()
    kb.button(text="⬅️ Назад", callback_data=SettingsCb(action="cancel_input", section=key))
    return _header(key) + FIELD_WAITING[field], kb.as_markup()


def _is_valid_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in ("http", "https") and bool(parsed.netloc) and " " not in value


# --- Роутер ------------------------------------------------------------------


def create_router(admin_chat_id: int) -> Router:
    router = Router(name="admin_settings")
    router.message.filter(F.chat.id == admin_chat_id)
    router.callback_query.filter(F.message.chat.id == admin_chat_id)

    async def ask_input(bot, chat_id: int, section: str, field: str, settings_msg_id: int, user_id: int, error: str = "") -> None:
        await prompts.ask(
            bot, chat_id, FIELD_PROMPT[field],
            kind="section", settings_msg_id=settings_msg_id, user_id=user_id,
            data={"section": section, "field": field},
            placeholder=FIELD_PLACEHOLDER[field], error=error,
        )

    @router.message(Command("settings"))
    async def cmd_settings(message: Message) -> None:
        await prompts.drop(message.bot, message.chat.id)
        text, markup = list_screen()
        await message.answer(text, reply_markup=markup)

    @router.callback_query(SettingsCb.filter(F.action == "list"))
    async def on_list(callback: CallbackQuery) -> None:
        await callback.answer()
        await prompts.drop(callback.bot, callback.message.chat.id)
        await edit_screen(callback.bot, callback.message.chat.id, callback.message.message_id, list_screen())

    @router.callback_query(SettingsCb.filter(F.action.in_({"open", "cancel_input"})))
    async def on_open(callback: CallbackQuery, callback_data: SettingsCb, db: Database) -> None:
        await callback.answer()
        await prompts.drop(callback.bot, callback.message.chat.id)
        screen = await _section_screen(db, callback_data.section)
        await edit_screen(callback.bot, callback.message.chat.id, callback.message.message_id, screen)

    @router.callback_query(SettingsCb.filter(F.action == "edit"))
    async def on_edit(callback: CallbackQuery, callback_data: SettingsCb) -> None:
        await callback.answer()
        chat_id = callback.message.chat.id
        key, field = callback_data.section, callback_data.field
        await edit_screen(callback.bot, chat_id, callback.message.message_id, _waiting_screen(key, field))
        await ask_input(callback.bot, chat_id, key, field, callback.message.message_id, callback.from_user.id)

    @router.callback_query(SettingsCb.filter(F.action == "delete"))
    async def on_delete(callback: CallbackQuery, callback_data: SettingsCb, db: Database) -> None:
        await callback.answer()
        key, field = callback_data.section, callback_data.field
        user_id = callback.from_user.id
        if field == "photo":
            await db.set_photo(key, None, user_id)
        elif field == "text":
            await db.set_text(key, "", user_id)
        elif field == "url":
            await db.set_setting(SECTION_URL_KEYS[key], None, user_id)
        screen = await _section_screen(db, key, note=FIELD_DELETED[field])
        await edit_screen(callback.bot, callback.message.chat.id, callback.message.message_id, screen)

    @router.message(prompts.filter("section"))
    async def on_input(message: Message, db: Database) -> None:
        p = await prompts.drop(message.bot, message.chat.id)
        section, field = p.data["section"], p.data["field"]
        with suppress(TelegramBadRequest):
            await message.delete()

        async def retry(error: str) -> None:
            await ask_input(message.bot, message.chat.id, section, field, p.settings_msg_id, p.user_id, error)

        user_id = message.from_user.id
        note = FIELD_SAVED[field]

        if field == "photo":
            if not message.photo:
                return await retry("Потрібне саме фото (не файлом).")
            await db.set_photo(section, message.photo[-1].file_id, user_id)

        elif field == "text":
            if not message.text:
                return await retry("Потрібен текст.")
            await db.set_text(section, message.html_text, user_id)
            content = await db.get_section(section)
            if content.photo_id and len(content.text) > CAPTION_LIMIT:
                note += (
                    f"\n⚠️ Текст довший за {CAPTION_LIMIT} символів — "
                    "фото і текст надсилатимуться двома повідомленнями."
                )

        elif field == "url":
            url = (message.text or "").strip()
            if not _is_valid_url(url):
                return await retry("Це не схоже на посилання. Воно має починатися з https://")
            await db.set_setting(SECTION_URL_KEYS[section], url, user_id)

        screen = await _section_screen(db, section, note=note)
        await edit_screen(message.bot, message.chat.id, p.settings_msg_id, screen)

    return router
