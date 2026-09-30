"""Меню /settings → Домашні групи → Список груп: фото, текст, лідер кожної групи."""

from contextlib import suppress
from html import escape

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.db import Database
from bot.events import html_to_plain
from bot.handlers.admin_common import HomeGroupCb, Screen, SettingsCb, edit_screen, prompts
from bot.homegroups import TEXT_LIMIT, HomeGroup
from bot.keyboards import url_button_kb
from bot.serving import parse_username

HEADER = "⚙️ <b>🏠 Домашні групи → 👥 Список груп</b>\n\n"
LABEL_MAX_LEN = 40

# Кроки додавання; лідера можна пропустити
ADD_FLOW = ["photo", "text", "leader"]
COLUMN = {"photo": "photo_id", "text": "text", "leader": "leader"}

PROMPT = {
    "photo": ("🖼 Надішліть у відповідь фото групи.", None),
    "text": (
        "📝 Надішліть у відповідь опис групи (коли, де, для кого). Перший рядок — назва групи. "
        "Форматування збережеться.",
        "Назва групи…",
    ),
    "leader": ("👤 Надішліть у відповідь @username лідера — кнопка «Написати лідеру» відкриє чат з цією людиною.", "@username"),
}
WAITING = {"photo": "🖼 Очікую фото…", "text": "📝 Очікую опис…", "leader": "👤 Очікую лідера…"}
SAVED = {"photo": "✅ Фото змінено.", "text": "✅ Опис змінено.", "leader": "✅ Лідера змінено."}


# --- Екрани ------------------------------------------------------------------


def _short(text: str) -> str:
    return text if len(text) <= LABEL_MAX_LEN else text[: LABEL_MAX_LEN - 1] + "…"


def _list_screen(groups: list[HomeGroup], note: str = "") -> Screen:
    kb = InlineKeyboardBuilder()
    for group in groups:
        kb.button(text=_short(group.title), callback_data=HomeGroupCb(action="open", group=group.id))
    kb.button(text="➕ Додати групу", callback_data=HomeGroupCb(action="add"))
    kb.button(text="⬅️ Назад", callback_data=SettingsCb(action="open", section="homegroups"))
    kb.adjust(1)
    text = HEADER + (
        "Ці сторінки люди гортають після кнопки «👥 Вибрати домашку». Оберіть групу або додайте нову."
        if groups else "Груп поки немає — додайте першу. Кнопка «👥 Вибрати домашку» з'явиться, щойно буде хоч одна."
    )
    if note:
        text = f"{note}\n\n{text}"
    return text, kb.as_markup()


def _group_screen(group: HomeGroup, note: str = "") -> Screen:
    kb = InlineKeyboardBuilder()
    for label, field in (("🖼 Фото", "photo"), ("📝 Опис", "text"), ("👤 Лідер", "leader")):
        kb.button(text=label, callback_data=HomeGroupCb(action="edit", group=group.id, value=field))
    kb.button(text="👁 Переглянути", callback_data=HomeGroupCb(action="preview", group=group.id))
    kb.button(text="🗑 Видалити", callback_data=HomeGroupCb(action="delete", group=group.id))
    kb.button(text="⬅️ До груп", callback_data=HomeGroupCb(action="list"))
    kb.adjust(3, 2, 1)

    none = "<i>не задано</i>"
    leader = f"@{escape(group.leader)}" if group.leader else f"{none} — кнопки «Написати лідеру» не буде"
    text = (
        f"{HEADER}<b>{escape(group.title)}</b>\n\n"
        f"👤 <b>Лідер:</b> {leader}\n\n"
        f"📝 <b>Опис:</b>\n{group.text or none}"
    )
    if note:
        text = f"{note}\n\n{text}"
    return text, kb.as_markup()


def _waiting_screen(group: HomeGroup | None, field: str, adding: bool) -> Screen:
    kb = InlineKeyboardBuilder()
    group_id = group.id if group else 0
    if adding and field == "leader":
        kb.button(text="➡️ Без лідера", callback_data=HomeGroupCb(action="skip", group=group_id))
    elif group and field == "leader" and group.leader:
        kb.button(text="🗑 Прибрати", callback_data=HomeGroupCb(action="clear", group=group_id, value=field))
    back = HomeGroupCb(action="cancel_input", group=group_id) if group else HomeGroupCb(action="list")
    kb.button(text="⬅️ Назад", callback_data=back)
    kb.adjust(1)
    step = f" (крок {ADD_FLOW.index(field) + 1} з {len(ADD_FLOW)})" if adding else ""
    return f"{HEADER}{WAITING[field]}{step}", kb.as_markup()


def _delete_screen(group: HomeGroup) -> Screen:
    kb = InlineKeyboardBuilder()
    kb.button(text="🗑 Так, видалити", callback_data=HomeGroupCb(action="delete_yes", group=group.id))
    kb.button(text="⬅️ Ні", callback_data=HomeGroupCb(action="open", group=group.id))
    kb.adjust(2)
    return f"{HEADER}Видалити групу «{escape(group.title)}»?", kb.as_markup()


# --- Роутер ------------------------------------------------------------------


def create_router(admin_chat_id: int) -> Router:
    router = Router(name="admin_homegroups")
    router.message.filter(F.chat.id == admin_chat_id)
    router.callback_query.filter(F.message.chat.id == admin_chat_id)

    async def list_screen(db: Database, note: str = "") -> Screen:
        return _list_screen(await db.list_groups(), note)

    async def ask(bot, chat_id: int, settings_msg_id: int, user_id: int, group: HomeGroup | None, field: str,
                  adding: bool = False, error: str = "") -> None:
        text, placeholder = PROMPT[field]
        await edit_screen(bot, chat_id, settings_msg_id, _waiting_screen(group, field, adding))
        await prompts.ask(
            bot, chat_id, text,
            kind="homegroup", settings_msg_id=settings_msg_id, user_id=user_id,
            data={"group": group.id if group else 0, "field": field, "adding": adding},
            placeholder=placeholder, error=error,
        )

    async def next_step(bot, chat_id: int, settings_msg_id: int, user_id: int, group: HomeGroup, field: str) -> None:
        index = ADD_FLOW.index(field) + 1
        if index < len(ADD_FLOW):
            return await ask(bot, chat_id, settings_msg_id, user_id, group, ADD_FLOW[index], adding=True)
        await edit_screen(bot, chat_id, settings_msg_id, _group_screen(group, "✅ Групу додано."))

    async def show(callback: CallbackQuery, screen: Screen) -> None:
        await edit_screen(callback.bot, callback.message.chat.id, callback.message.message_id, screen)

    @router.callback_query(HomeGroupCb.filter(F.action == "list"))
    async def on_list(callback: CallbackQuery, db: Database) -> None:
        await callback.answer()
        await prompts.drop(callback.bot, callback.message.chat.id)
        await show(callback, await list_screen(db))

    @router.callback_query(HomeGroupCb.filter(F.action == "add"))
    async def on_add(callback: CallbackQuery) -> None:
        await callback.answer()
        await ask(callback.bot, callback.message.chat.id, callback.message.message_id,
                  callback.from_user.id, None, "photo", adding=True)

    @router.callback_query(HomeGroupCb.filter())
    async def on_group_action(callback: CallbackQuery, callback_data: HomeGroupCb, db: Database) -> None:
        await callback.answer()
        chat_id = callback.message.chat.id
        await prompts.drop(callback.bot, chat_id)

        group = await db.get_group(callback_data.group)
        if not group:
            return await show(callback, await list_screen(db, note="⚠️ Цю групу вже видалено."))

        action, field = callback_data.action, callback_data.value
        if action == "edit" and field in PROMPT:
            return await ask(callback.bot, chat_id, callback.message.message_id, callback.from_user.id, group, field)
        if action == "preview":
            markup = url_button_kb("✉️ Написати лідеру", f"https://t.me/{group.leader}") if group.leader else None
            await callback.message.answer_photo(group.photo_id, caption=group.text or None, reply_markup=markup)
            return
        if action == "delete":
            return await show(callback, _delete_screen(group))
        if action == "delete_yes":
            await db.delete_group(group.id)
            return await show(callback, await list_screen(db, note="🗑 Групу видалено."))
        if action == "skip":  # «Без лідера» — останній крок додавання
            return await next_step(callback.bot, chat_id, callback.message.message_id, callback.from_user.id,
                                   group, "leader")

        note = ""
        if action == "clear" and field == "leader":
            await db.update_group(group.id, "leader", None)
            group = await db.get_group(group.id)
            note = "🗑 Лідера прибрано."
        await show(callback, _group_screen(group, note))  # open, cancel_input, clear

    @router.message(prompts.filter("homegroup"))
    async def on_input(message: Message, db: Database) -> None:
        p = await prompts.drop(message.bot, message.chat.id)
        group_id, field, adding = p.data["group"], p.data["field"], p.data["adding"]
        with suppress(TelegramBadRequest):
            await message.delete()

        chat_id = message.chat.id
        group = await db.get_group(group_id) if group_id else None
        if group_id and not group:
            return await edit_screen(message.bot, chat_id, p.settings_msg_id,
                                     await list_screen(db, note="⚠️ Цю групу вже видалено."))

        async def retry(error: str) -> None:
            await ask(message.bot, chat_id, p.settings_msg_id, p.user_id, group, field, adding, error)

        if field == "photo":
            if not message.photo:
                return await retry("Потрібне саме фото (не файлом).")
            photo_id = message.photo[-1].file_id
            if group:
                await db.update_group(group.id, "photo_id", photo_id)
            else:
                group_id = await db.add_group(photo_id)
        elif field == "text":
            if not message.text:
                return await retry("Потрібен текст.")
            plain_len = len(html_to_plain(message.html_text))
            if plain_len > TEXT_LIMIT:
                return await retry(
                    f"Задовгий опис ({plain_len} символів, максимум {TEXT_LIMIT}) — підпис під фото в Telegram обмежений."
                )
            await db.update_group(group.id, "text", message.html_text)
        elif field == "leader":
            username = parse_username(message.text or "")
            if not username:
                return await retry("Не схоже на @username. Приклад: @ivan_petrenko")
            await db.update_group(group.id, "leader", username)

        group = await db.get_group(group_id)
        if adding:
            return await next_step(message.bot, chat_id, p.settings_msg_id, p.user_id, group, field)
        await edit_screen(message.bot, chat_id, p.settings_msg_id, _group_screen(group, SAVED[field]))

    return router
