"""Меню /settings → Потреба в служінні: назва, короткий опис, повний опис, відповідальний."""

from contextlib import suppress
from html import escape

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.db import Database
from bot.handlers.admin_common import Screen, ServingCb, SettingsCb, edit_screen, prompts
from bot.handlers.serving_user import need_view
from bot.serving import DESCRIPTION_MAX_LEN, TITLE_MAX_LEN, Need, parse_username

HEADER = "⚙️ <b>🙌 Потреба в служінні</b>\n\n"

# Кроки додавання; відповідального можна пропустити
ADD_FLOW = ["title", "description", "responsible"]

PROMPT = {
    "title": (f"✏️ Надішліть у відповідь назву служіння (до {TITLE_MAX_LEN} символів). Можна з емодзі.", "🎸 Прославлення"),
    "description": (
        "📄 Надішліть у відповідь опис — його побачать, відкривши це служіння. Форматування збережеться.",
        "Детальний опис…",
    ),
    "responsible": (
        "👤 Надішліть у відповідь @username відповідального. Ця людина отримуватиме відгуки особисто "
        "(для цього їй треба хоч раз надіслати боту /start).",
        "@username",
    ),
}
WAITING = {
    "title": "✏️ Очікую назву…",
    "description": "📄 Очікую опис…",
    "responsible": "👤 Очікую відповідального…",
}
SAVED = {
    "title": "✅ Назву змінено.",
    "description": "✅ Опис змінено.",
    "responsible": "✅ Відповідального змінено.",
}


# --- Екрани ------------------------------------------------------------------


def _list_screen(needs: list[Need], note: str = "") -> Screen:
    kb = InlineKeyboardBuilder()
    for need in needs:
        kb.button(text=need.title, callback_data=ServingCb(action="open", need=need.id))
    kb.button(text="➕ Додати потребу", callback_data=ServingCb(action="add"))
    kb.button(text="⬅️ Назад", callback_data=SettingsCb(action="list"))
    kb.adjust(1)
    text = HEADER + ("Оберіть потребу, щоб змінити її, або додайте нову." if needs else "Потреб поки немає — додайте першу.")
    if note:
        text = f"{note}\n\n{text}"
    return text, kb.as_markup()


async def _need_screen(db: Database, need: Need, note: str = "") -> Screen:
    kb = InlineKeyboardBuilder()
    for label, field in (("✏️ Назва", "title"), ("📄 Опис", "description"), ("👤 Відповідальний", "responsible")):
        kb.button(text=label, callback_data=ServingCb(action="edit", need=need.id, value=field))
    kb.button(text="👁 Переглянути", callback_data=ServingCb(action="preview", need=need.id))
    kb.button(text="🗑 Видалити", callback_data=ServingCb(action="delete", need=need.id))
    kb.button(text="⬅️ До потреб", callback_data=ServingCb(action="list"))
    kb.adjust(3, 2, 1)

    none = "<i>не задано</i>"
    if need.responsible:
        known = await db.find_user_id(need.responsible)
        status = "отримуватиме відгуки особисто" if known else "⚠️ бот ще не знає цю людину — хай надішле боту /start"
        responsible = f"@{escape(need.responsible)} ({status})"
    else:
        responsible = f"{none} — відгуки лише в цю групу"

    text = (
        f"{HEADER}<b>{escape(need.title)}</b>\n\n"
        f"👤 <b>Відповідальний:</b> {responsible}\n\n"
        f"📄 <b>Опис:</b>\n{need.description or none}"
    )
    if note:
        text = f"{note}\n\n{text}"
    return text, kb.as_markup()


def _waiting_screen(need: Need | None, field: str, adding: bool) -> Screen:
    kb = InlineKeyboardBuilder()
    need_id = need.id if need else 0
    if adding and field == "responsible":
        kb.button(text="➡️ Без відповідального", callback_data=ServingCb(action="skip", need=need_id))
    elif need and field == "responsible" and need.responsible:
        kb.button(text="🗑 Прибрати", callback_data=ServingCb(action="clear", need=need_id, value=field))
    back = ServingCb(action="cancel_input", need=need_id) if need else ServingCb(action="list")
    kb.button(text="⬅️ Назад", callback_data=back)
    kb.adjust(1)
    step = f" (крок {ADD_FLOW.index(field) + 1} з {len(ADD_FLOW)})" if adding else ""
    return f"{HEADER}{WAITING[field]}{step}", kb.as_markup()


def _delete_screen(need: Need) -> Screen:
    kb = InlineKeyboardBuilder()
    kb.button(text="🗑 Так, видалити", callback_data=ServingCb(action="delete_yes", need=need.id))
    kb.button(text="⬅️ Ні", callback_data=ServingCb(action="open", need=need.id))
    kb.adjust(2)
    return f"{HEADER}Видалити потребу «{escape(need.title)}»?", kb.as_markup()


# --- Роутер ------------------------------------------------------------------


def create_router(admin_chat_id: int) -> Router:
    router = Router(name="admin_serving")
    router.message.filter(F.chat.id == admin_chat_id)
    router.callback_query.filter(F.message.chat.id == admin_chat_id)

    async def list_screen(db: Database, note: str = "") -> Screen:
        return _list_screen(await db.list_needs(), note)

    async def ask(bot, chat_id: int, settings_msg_id: int, user_id: int, need: Need | None, field: str,
                  adding: bool = False, error: str = "") -> None:
        text, placeholder = PROMPT[field]
        await edit_screen(bot, chat_id, settings_msg_id, _waiting_screen(need, field, adding))
        await prompts.ask(
            bot, chat_id, text,
            kind="serving", settings_msg_id=settings_msg_id, user_id=user_id,
            data={"need": need.id if need else 0, "field": field, "adding": adding},
            placeholder=placeholder, error=error,
        )

    async def next_step(bot, chat_id: int, settings_msg_id: int, user_id: int, need: Need, field: str, db: Database) -> None:
        index = ADD_FLOW.index(field) + 1
        if index < len(ADD_FLOW):
            return await ask(bot, chat_id, settings_msg_id, user_id, need, ADD_FLOW[index], adding=True)
        await edit_screen(bot, chat_id, settings_msg_id, await _need_screen(db, need, "✅ Потребу додано."))

    async def show(callback: CallbackQuery, screen: Screen) -> None:
        await edit_screen(callback.bot, callback.message.chat.id, callback.message.message_id, screen)

    @router.callback_query(ServingCb.filter(F.action == "list"))
    async def on_list(callback: CallbackQuery, db: Database) -> None:
        await callback.answer()
        await prompts.drop(callback.bot, callback.message.chat.id)
        await show(callback, await list_screen(db))

    @router.callback_query(ServingCb.filter(F.action == "add"))
    async def on_add(callback: CallbackQuery) -> None:
        await callback.answer()
        await ask(callback.bot, callback.message.chat.id, callback.message.message_id,
                  callback.from_user.id, None, "title", adding=True)

    @router.callback_query(ServingCb.filter())
    async def on_need_action(callback: CallbackQuery, callback_data: ServingCb, db: Database) -> None:
        await callback.answer()
        chat_id = callback.message.chat.id
        await prompts.drop(callback.bot, chat_id)

        need = await db.get_need(callback_data.need)
        if not need:
            return await show(callback, await list_screen(db, note="⚠️ Цю потребу вже видалено."))

        action, field = callback_data.action, callback_data.value
        if action == "edit" and field in PROMPT:
            return await ask(callback.bot, chat_id, callback.message.message_id, callback.from_user.id, need, field)
        if action == "preview":
            text, _ = need_view(need, joined=False)
            await callback.message.answer(text)
            return
        if action == "delete":
            return await show(callback, _delete_screen(need))
        if action == "delete_yes":
            await db.delete_need(need.id)
            return await show(callback, await list_screen(db, note="🗑 Потребу видалено."))
        if action == "skip":  # «Без відповідального» — останній крок додавання
            return await next_step(callback.bot, chat_id, callback.message.message_id, callback.from_user.id,
                                   need, "responsible", db)

        note = ""
        if action == "clear" and field == "responsible":
            await db.update_need(need.id, "responsible", None)
            need = await db.get_need(need.id)
            note = "🗑 Відповідального прибрано."
        await show(callback, await _need_screen(db, need, note))  # open, cancel_input, clear

    @router.message(prompts.filter("serving"))
    async def on_input(message: Message, db: Database) -> None:
        p = await prompts.drop(message.bot, message.chat.id)
        need_id, field, adding = p.data["need"], p.data["field"], p.data["adding"]
        with suppress(TelegramBadRequest):
            await message.delete()

        chat_id = message.chat.id
        need = await db.get_need(need_id) if need_id else None
        if need_id and not need:
            return await edit_screen(message.bot, chat_id, p.settings_msg_id,
                                     await list_screen(db, note="⚠️ Цю потребу вже видалено."))

        async def retry(error: str) -> None:
            await ask(message.bot, chat_id, p.settings_msg_id, p.user_id, need, field, adding, error)

        value = (message.text or "").strip()
        if not value:
            return await retry("Потрібен текст.")

        if field == "title":
            if len(value) > TITLE_MAX_LEN:
                return await retry(f"Задовга назва ({len(value)} символів, максимум {TITLE_MAX_LEN}).")
            if need:
                await db.update_need(need.id, "title", value)
            else:
                need_id = await db.add_need(value)
        elif field == "description":
            if len(value) > DESCRIPTION_MAX_LEN:
                return await retry(f"Задовго ({len(value)} символів, максимум {DESCRIPTION_MAX_LEN}).")
            await db.update_need(need.id, "description", message.html_text)
        elif field == "responsible":
            username = parse_username(value)
            if not username:
                return await retry("Не схоже на @username. Приклад: @ivan_petrenko")
            await db.update_need(need.id, "responsible", username)

        need = await db.get_need(need_id)
        if adding:
            return await next_step(message.bot, chat_id, p.settings_msg_id, p.user_id, need, field, db)
        await edit_screen(message.bot, chat_id, p.settings_msg_id, await _need_screen(db, need, SAVED[field]))

    return router
