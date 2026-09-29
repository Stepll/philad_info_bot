"""Меню /settings → Розклад: блоки розкладу редагуються кнопками."""

from contextlib import suppress
from html import escape

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.db import Database
from bot.handlers.admin_common import Screen, ScheduleCb, SettingsCb, edit_screen, prompts
from bot.render import invalidate_schedule, send_schedule
from bot.schedule import COLORS, DAYS_FULL, DAYS_SHORT, DEFAULT_COLOR, TITLE_MAX_LEN, ScheduleItem, parse_time

HEADER = "⚙️ <b>🕐 Розклад</b>\n\n"
NEW_ITEM_TIME = "12:00"
NEW_ITEM_TITLE = "Нова подія"
ADDED = "added"  # маркер останнього кроку додавання блоку

PROMPTS = {
    "time": ("🕐 Надішліть у відповідь час початку, напр. <code>19:00</code> або <code>7:30</code>.", "19:00"),
    "title": (f"✏️ Надішліть у відповідь назву (до {TITLE_MAX_LEN} символів).", "Назва події"),
}


# --- Екрани ------------------------------------------------------------------


def _item_label(item: ScheduleItem) -> str:
    return f"{COLORS.get(item.color, COLORS[DEFAULT_COLOR]).emoji} {DAYS_SHORT[item.day]} · {item.time} · {item.title}"


def _list_screen(items: list[ScheduleItem], note: str = "") -> Screen:
    kb = InlineKeyboardBuilder()
    for item in items:
        kb.button(text=_item_label(item), callback_data=ScheduleCb(action="item", item=item.id))
    kb.button(text="➕ Додати блок", callback_data=ScheduleCb(action="add"))
    kb.button(text="🖼 Переглянути", callback_data=ScheduleCb(action="preview"))
    kb.button(text="⬅️ Назад", callback_data=SettingsCb(action="list"))
    kb.adjust(*([1] * len(items)), 2, 1)

    text = HEADER + (
        "Оберіть блок, щоб змінити його, або додайте новий." if items else "Розклад порожній — додайте перший блок."
    )
    if note:
        text = f"{note}\n\n{text}"
    return text, kb.as_markup()


def _item_screen(item: ScheduleItem, note: str = "") -> Screen:
    color = COLORS.get(item.color, COLORS[DEFAULT_COLOR])
    kb = InlineKeyboardBuilder()
    kb.button(text="📅 День", callback_data=ScheduleCb(action="day", item=item.id))
    kb.button(text="🕐 Час", callback_data=ScheduleCb(action="time", item=item.id))
    kb.button(text="✏️ Назва", callback_data=ScheduleCb(action="title", item=item.id))
    kb.button(text="🎨 Колір", callback_data=ScheduleCb(action="color", item=item.id))
    kb.button(text="🗑 Видалити блок", callback_data=ScheduleCb(action="delete", item=item.id))
    kb.button(text="⬅️ До розкладу", callback_data=ScheduleCb(action="list"))
    kb.adjust(2, 2, 1, 1)

    text = (
        f"{HEADER}"
        f"📅 <b>День:</b> {DAYS_FULL[item.day]}\n"
        f"🕐 <b>Час:</b> {item.time}\n"
        f"✏️ <b>Назва:</b> {escape(item.title)}\n"
        f"🎨 <b>Колір:</b> {color.emoji} {color.name}"
    )
    if note:
        text = f"{note}\n\n{text}"
    return text, kb.as_markup()


def _day_screen(item_id: int, action: str, back: ScheduleCb) -> Screen:
    kb = InlineKeyboardBuilder()
    for day, label in enumerate(DAYS_SHORT):
        kb.button(text=label, callback_data=ScheduleCb(action=action, item=item_id, value=str(day)))
    kb.button(text="⬅️ Назад", callback_data=back)
    kb.adjust(4, 3, 1)
    return HEADER + "📅 Оберіть день:", kb.as_markup()


def _color_screen(item_id: int) -> Screen:
    kb = InlineKeyboardBuilder()
    for key, color in COLORS.items():
        kb.button(text=f"{color.emoji} {color.name}", callback_data=ScheduleCb(action="set_color", item=item_id, value=key))
    kb.button(text="⬅️ Назад", callback_data=ScheduleCb(action="item", item=item_id))
    kb.adjust(*([2] * ((len(COLORS) + 1) // 2)), 1)
    return HEADER + "🎨 Оберіть колір:", kb.as_markup()


def _delete_screen(item: ScheduleItem) -> Screen:
    kb = InlineKeyboardBuilder()
    kb.button(text="🗑 Так, видалити", callback_data=ScheduleCb(action="delete_yes", item=item.id))
    kb.button(text="⬅️ Ні", callback_data=ScheduleCb(action="item", item=item.id))
    kb.adjust(2)
    return f"{HEADER}Видалити блок «{escape(item.title)}» ({DAYS_SHORT[item.day]} {item.time})?", kb.as_markup()


def _waiting_screen(item_id: int, field: str) -> Screen:
    kb = InlineKeyboardBuilder()
    kb.button(text="⬅️ Назад", callback_data=ScheduleCb(action="cancel_input", item=item_id))
    waiting = "🕐 Очікую час початку…" if field == "time" else "✏️ Очікую назву…"
    return HEADER + waiting, kb.as_markup()


# --- Роутер ------------------------------------------------------------------


def create_router(admin_chat_id: int) -> Router:
    router = Router(name="admin_schedule")
    router.message.filter(F.chat.id == admin_chat_id)
    router.callback_query.filter(F.message.chat.id == admin_chat_id)

    async def show(callback: CallbackQuery, screen: Screen) -> None:
        await edit_screen(callback.bot, callback.message.chat.id, callback.message.message_id, screen)

    async def show_list(callback: CallbackQuery, db: Database, note: str = "") -> None:
        await show(callback, _list_screen(await db.list_schedule(), note))

    async def ask(bot, chat_id: int, settings_msg_id: int, user_id: int, item_id: int, field: str,
                  then: str = "", error: str = "") -> None:
        text, placeholder = PROMPTS[field]
        await edit_screen(bot, chat_id, settings_msg_id, _waiting_screen(item_id, field))
        await prompts.ask(
            bot, chat_id, text,
            kind="schedule", settings_msg_id=settings_msg_id, user_id=user_id,
            data={"item": item_id, "field": field, "then": then},
            placeholder=placeholder, error=error,
        )

    @router.callback_query(ScheduleCb.filter(F.action == "list"))
    async def on_list(callback: CallbackQuery, db: Database) -> None:
        await callback.answer()
        await prompts.drop(callback.bot, callback.message.chat.id)
        await show_list(callback, db)

    @router.callback_query(ScheduleCb.filter(F.action == "preview"))
    async def on_preview(callback: CallbackQuery, db: Database) -> None:
        await callback.answer("Генерую…")
        await send_schedule(callback.bot, callback.message.chat.id, db)

    # Додавання: день → час → назва
    @router.callback_query(ScheduleCb.filter(F.action == "add"))
    async def on_add(callback: CallbackQuery) -> None:
        await callback.answer()
        await prompts.drop(callback.bot, callback.message.chat.id)
        await show(callback, _day_screen(0, "add_day", back=ScheduleCb(action="list")))

    @router.callback_query(ScheduleCb.filter(F.action == "add_day"))
    async def on_add_day(callback: CallbackQuery, callback_data: ScheduleCb, db: Database) -> None:
        await callback.answer()
        item_id = await db.add_schedule_item(int(callback_data.value), NEW_ITEM_TIME, NEW_ITEM_TITLE, DEFAULT_COLOR)
        await invalidate_schedule(db)
        await ask(callback.bot, callback.message.chat.id, callback.message.message_id,
                  callback.from_user.id, item_id, "time", then="title")

    # Решта дій — над конкретним блоком
    @router.callback_query(ScheduleCb.filter())
    async def on_item_action(callback: CallbackQuery, callback_data: ScheduleCb, db: Database) -> None:
        await callback.answer()
        chat_id = callback.message.chat.id
        await prompts.drop(callback.bot, chat_id)

        item = await db.get_schedule_item(callback_data.item)
        if not item:
            return await show_list(callback, db, note="⚠️ Цей блок уже видалено.")

        action, value = callback_data.action, callback_data.value
        note = ""

        if action == "day":
            return await show(callback, _day_screen(item.id, "set_day", back=ScheduleCb(action="item", item=item.id)))
        if action == "color":
            return await show(callback, _color_screen(item.id))
        if action == "delete":
            return await show(callback, _delete_screen(item))
        if action in ("time", "title"):
            return await ask(callback.bot, chat_id, callback.message.message_id, callback.from_user.id, item.id, action)

        if action == "delete_yes":
            await db.delete_schedule_item(item.id)
            await invalidate_schedule(db)
            return await show_list(callback, db, note="🗑 Блок видалено.")
        if action == "set_day" and value.isdigit() and int(value) < 7:
            await db.update_schedule_item(item.id, "day", int(value))
            note = "✅ День змінено."
        elif action == "set_color" and value in COLORS:
            await db.update_schedule_item(item.id, "color", value)
            note = "✅ Колір змінено."

        if note:
            await invalidate_schedule(db)
            item = await db.get_schedule_item(item.id)
        await show(callback, _item_screen(item, note))  # "item", "cancel_input" і після змін

    @router.message(prompts.filter("schedule"))
    async def on_input(message: Message, db: Database) -> None:
        p = await prompts.drop(message.bot, message.chat.id)
        item_id, field, then = p.data["item"], p.data["field"], p.data["then"]
        with suppress(TelegramBadRequest):
            await message.delete()

        chat_id = message.chat.id
        if not await db.get_schedule_item(item_id):
            items = await db.list_schedule()
            return await edit_screen(message.bot, chat_id, p.settings_msg_id, _list_screen(items, "⚠️ Цей блок уже видалено."))

        async def retry(error: str) -> None:
            await ask(message.bot, chat_id, p.settings_msg_id, p.user_id, item_id, field, then, error)

        value = (message.text or "").strip()
        if field == "time":
            time = parse_time(value)
            if not time:
                return await retry("Не вдалося розпізнати час. Формат: 19:00")
            await db.update_schedule_item(item_id, "time", time)
            note = "✅ Час змінено."
        else:
            if not value:
                return await retry("Потрібен текст.")
            if len(value) > TITLE_MAX_LEN:
                return await retry(f"Задовга назва ({len(value)} символів, максимум {TITLE_MAX_LEN}).")
            await db.update_schedule_item(item_id, "title", value)
            note = "✅ Назву змінено."
        await invalidate_schedule(db)

        # Під час додавання блоку після часу одразу питаємо назву
        if then in PROMPTS:
            return await ask(message.bot, chat_id, p.settings_msg_id, p.user_id, item_id, then, then=ADDED)
        if then == ADDED:
            note = "✅ Блок додано. Колір можна змінити нижче."
        item = await db.get_schedule_item(item_id)
        await edit_screen(message.bot, chat_id, p.settings_msg_id, _item_screen(item, note))

    return router
