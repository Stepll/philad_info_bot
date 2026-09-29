"""Меню /settings → Події: постер, текст, дата, час, місце, посилання."""

from contextlib import suppress
from datetime import timedelta
from html import escape

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.config import Config
from bot.db import Database
from bot.events import (
    EVENT_TEXT_LIMIT,
    KEEP_PAST_DAYS,
    PLACE_MAX_LEN,
    Event,
    caption,
    format_date,
    html_to_plain,
    parse_date,
)
from bot.handlers.admin_common import EventCb, Screen, SettingsCb, edit_screen, is_valid_url, prompts
from bot.keyboards import url_button_kb
from bot.schedule import parse_time

HEADER = "⚙️ <b>📅 Події</b>\n\n"
LABEL_MAX_LEN = 40

# Кроки додавання події; час і місце — пізніше, з екрана події
ADD_FLOW = ["poster", "text", "date", "url"]
OPTIONAL_FIELDS = {"time", "place", "url"}
COLUMN = {"poster": "poster_id", "text": "text", "date": "date", "time": "time", "place": "place", "url": "url"}

PROMPT = {
    "poster": ("🖼 Надішліть у відповідь на це повідомлення постер (фото).", None),
    "text": (
        "📝 Надішліть у відповідь текст події. Перший рядок — назва (так подія називатиметься в календарі). "
        "Форматування збережеться.",
        "Назва події…",
    ),
    "date": ("📅 Надішліть у відповідь дату у форматі <code>12.10.2026</code>.", "12.10.2026"),
    "time": ("🕐 Надішліть у відповідь час початку, напр. <code>18:00</code>.", "18:00"),
    "place": ("📍 Надішліть у відповідь місце проведення.", "Головний зал"),
    "url": ("🔗 Надішліть у відповідь посилання (реєстрація, форма тощо).", "https://..."),
}
WAITING = {
    "poster": "🖼 Очікую постер…",
    "text": "📝 Очікую текст…",
    "date": "📅 Очікую дату…",
    "time": "🕐 Очікую час…",
    "place": "📍 Очікую місце…",
    "url": "🔗 Очікую посилання…",
}
SAVED = {
    "poster": "✅ Постер змінено.",
    "text": "✅ Текст змінено.",
    "date": "✅ Дату змінено.",
    "time": "✅ Час змінено.",
    "place": "✅ Місце змінено.",
    "url": "✅ Посилання змінено.",
}
CLEARED = {"time": "🗑 Час прибрано.", "place": "🗑 Місце прибрано.", "url": "🗑 Посилання прибрано."}


# --- Екрани ------------------------------------------------------------------


def _short(text: str) -> str:
    return text if len(text) <= LABEL_MAX_LEN else text[: LABEL_MAX_LEN - 1] + "…"


def _event_label(event: Event, today) -> str:
    if not event.day:
        return f"📝 Чернетка · {_short(event.title)}"
    mark = "🕓 " if event.day < today else ""
    return f"{mark}{format_date(event.day)} · {_short(event.title)}"


def _list_screen(events: list[Event], today, note: str = "") -> Screen:
    kb = InlineKeyboardBuilder()
    for event in events:
        kb.button(text=_event_label(event, today), callback_data=EventCb(action="open", event=event.id))
    kb.button(text="➕ Додати подію", callback_data=EventCb(action="add"))
    kb.button(text="⬅️ Назад", callback_data=SettingsCb(action="list"))
    kb.adjust(1)

    if events:
        text = "Оберіть подію, щоб змінити її, або додайте нову.\n\n📝 — чернетка без дати, 🕓 — минула (людям не показуються)."
    else:
        text = "Подій поки немає — додайте першу."
    text = HEADER + text
    if note:
        text = f"{note}\n\n{text}"
    return text, kb.as_markup()


def _event_screen(event: Event, today, in_calendar: int, note: str = "") -> Screen:
    kb = InlineKeyboardBuilder()
    buttons = [
        ("🖼 Постер", "poster"), ("📝 Текст", "text"),
        ("📅 Дата", "date"), ("🕐 Час", "time"),
        ("📍 Місце", "place"), ("🔗 Посилання", "url"),
    ]
    for label, field in buttons:
        kb.button(text=label, callback_data=EventCb(action="edit", event=event.id, value=field))
    kb.button(text="👁 Переглянути", callback_data=EventCb(action="preview", event=event.id))
    kb.button(text="🗑 Видалити", callback_data=EventCb(action="delete", event=event.id))
    kb.button(text="⬅️ До подій", callback_data=EventCb(action="list"))
    kb.adjust(2, 2, 2, 2, 1)

    none = "<i>не задано</i>"
    if not event.day:
        status = "📝 Чернетка — людям не показується, поки не задана дата."
    elif event.day < today:
        purge = format_date(event.day + timedelta(days=KEEP_PAST_DAYS))
        status = f"🕓 Подія минула — людям не показується. Буде видалена {purge}."
    else:
        status = f"✅ Показується людям. Додали в календар: {in_calendar}."

    text = (
        f"{HEADER}<b>{escape(event.title)}</b>\n{status}\n\n"
        f"📅 <b>Дата:</b> {format_date(event.day) if event.day else none}\n"
        f"🕐 <b>Час:</b> {event.time or none}\n"
        f"📍 <b>Місце:</b> {escape(event.place) if event.place else none}\n"
        f"🔗 <b>Посилання:</b> {escape(event.url) if event.url else none}\n\n"
        f"📝 <b>Текст:</b>\n{event.text or none}"
    )
    if note:
        text = f"{note}\n\n{text}"
    return text, kb.as_markup()


def _waiting_screen(event: Event | None, field: str, adding: bool) -> Screen:
    kb = InlineKeyboardBuilder()
    event_id = event.id if event else 0
    if adding and field == "url":
        kb.button(text="➡️ Без посилання", callback_data=EventCb(action="skip", event=event_id))
    elif event and field in OPTIONAL_FIELDS and getattr(event, field):
        kb.button(text="🗑 Прибрати", callback_data=EventCb(action="clear", event=event_id, value=field))
    back = EventCb(action="cancel_input", event=event_id) if event else EventCb(action="list")
    kb.button(text="⬅️ Назад", callback_data=back)
    kb.adjust(1)
    step = f" (крок {ADD_FLOW.index(field) + 1} з {len(ADD_FLOW)})" if adding else ""
    return f"{HEADER}{WAITING[field]}{step}", kb.as_markup()


def _delete_screen(event: Event) -> Screen:
    kb = InlineKeyboardBuilder()
    kb.button(text="🗑 Так, видалити", callback_data=EventCb(action="delete_yes", event=event.id))
    kb.button(text="⬅️ Ні", callback_data=EventCb(action="open", event=event.id))
    kb.adjust(2)
    return f"{HEADER}Видалити подію «{escape(event.title)}»?", kb.as_markup()


# --- Роутер ------------------------------------------------------------------


def create_router(admin_chat_id: int) -> Router:
    router = Router(name="admin_events")
    router.message.filter(F.chat.id == admin_chat_id)
    router.callback_query.filter(F.message.chat.id == admin_chat_id)

    async def list_screen(db: Database, config: Config, note: str = "") -> Screen:
        today = config.today()
        await db.purge_events_before(today - timedelta(days=KEEP_PAST_DAYS))
        return _list_screen(await db.list_events(), today, note)

    async def event_screen(db: Database, config: Config, event: Event, note: str = "") -> Screen:
        return _event_screen(event, config.today(), await db.calendar_count(event.id), note)

    async def ask(bot, chat_id: int, settings_msg_id: int, user_id: int, event: Event | None, field: str,
                  adding: bool = False, error: str = "") -> None:
        text, placeholder = PROMPT[field]
        await edit_screen(bot, chat_id, settings_msg_id, _waiting_screen(event, field, adding))
        await prompts.ask(
            bot, chat_id, text,
            kind="event", settings_msg_id=settings_msg_id, user_id=user_id,
            data={"event": event.id if event else 0, "field": field, "adding": adding},
            placeholder=placeholder, error=error,
        )

    async def next_step(bot, chat_id: int, settings_msg_id: int, user_id: int, event: Event, field: str,
                        db: Database, config: Config) -> None:
        """Після кроку додавання — наступний крок або екран готової події."""
        index = ADD_FLOW.index(field) + 1
        if index < len(ADD_FLOW):
            return await ask(bot, chat_id, settings_msg_id, user_id, event, ADD_FLOW[index], adding=True)
        note = "✅ Подію додано. Час і місце можна задати кнопками нижче."
        await edit_screen(bot, chat_id, settings_msg_id, await event_screen(db, config, event, note))

    async def show(callback: CallbackQuery, screen: Screen) -> None:
        await edit_screen(callback.bot, callback.message.chat.id, callback.message.message_id, screen)

    @router.callback_query(EventCb.filter(F.action == "list"))
    async def on_list(callback: CallbackQuery, db: Database, config: Config) -> None:
        await callback.answer()
        await prompts.drop(callback.bot, callback.message.chat.id)
        await show(callback, await list_screen(db, config))

    @router.callback_query(EventCb.filter(F.action == "add"))
    async def on_add(callback: CallbackQuery) -> None:
        await callback.answer()
        await ask(callback.bot, callback.message.chat.id, callback.message.message_id,
                  callback.from_user.id, None, "poster", adding=True)

    @router.callback_query(EventCb.filter())
    async def on_event_action(callback: CallbackQuery, callback_data: EventCb, db: Database, config: Config) -> None:
        chat_id = callback.message.chat.id
        await prompts.drop(callback.bot, chat_id)

        event = await db.get_event(callback_data.event)
        if not event:
            await callback.answer()
            return await show(callback, await list_screen(db, config, note="⚠️ Цю подію вже видалено."))

        action, field = callback_data.action, callback_data.value

        if action == "preview":
            await callback.answer()
            markup = url_button_kb("🔗 Детальніше", event.url) if event.url else None
            await callback.message.answer_photo(event.poster_id, caption=caption(event), reply_markup=markup)
            return

        await callback.answer()
        if action == "edit" and field in COLUMN:
            return await ask(callback.bot, chat_id, callback.message.message_id, callback.from_user.id, event, field)
        if action == "delete":
            return await show(callback, _delete_screen(event))
        if action == "delete_yes":
            await db.delete_event(event.id)
            return await show(callback, await list_screen(db, config, note="🗑 Подію видалено."))
        if action == "skip":  # «Без посилання» — останній крок додавання
            return await next_step(callback.bot, chat_id, callback.message.message_id, callback.from_user.id,
                                   event, "url", db, config)

        note = ""
        if action == "clear" and field in OPTIONAL_FIELDS:
            await db.update_event(event.id, COLUMN[field], None)
            event = await db.get_event(event.id)
            note = CLEARED[field]
        await show(callback, await event_screen(db, config, event, note))  # open, cancel_input, clear

    @router.message(prompts.filter("event"))
    async def on_input(message: Message, db: Database, config: Config) -> None:
        p = await prompts.drop(message.bot, message.chat.id)
        event_id, field, adding = p.data["event"], p.data["field"], p.data["adding"]
        with suppress(TelegramBadRequest):
            await message.delete()

        chat_id = message.chat.id
        event = await db.get_event(event_id) if event_id else None
        if event_id and not event:
            screen = await list_screen(db, config, note="⚠️ Цю подію вже видалено.")
            return await edit_screen(message.bot, chat_id, p.settings_msg_id, screen)

        async def retry(error: str) -> None:
            await ask(message.bot, chat_id, p.settings_msg_id, p.user_id, event, field, adding, error)

        value = (message.text or "").strip()

        if field == "poster":
            if not message.photo:
                return await retry("Потрібне саме фото (не файлом).")
            poster_id = message.photo[-1].file_id
            if event:
                await db.update_event(event.id, "poster_id", poster_id)
            else:
                event_id = await db.add_event(poster_id)
        elif field == "text":
            if not value:
                return await retry("Потрібен текст.")
            plain_len = len(html_to_plain(message.html_text))
            if plain_len > EVENT_TEXT_LIMIT:
                return await retry(
                    f"Задовгий текст ({plain_len} символів, максимум {EVENT_TEXT_LIMIT}) — "
                    "підпис під постером у Telegram обмежений."
                )
            await db.update_event(event.id, "text", message.html_text)
        elif field == "date":
            day = parse_date(value)
            if not day:
                return await retry("Не вдалося розпізнати дату. Формат: 12.10.2026")
            if day < config.today():
                return await retry("Ця дата вже минула.")
            await db.update_event(event.id, "date", day.isoformat())
        elif field == "time":
            time = parse_time(value)
            if not time:
                return await retry("Не вдалося розпізнати час. Формат: 18:00")
            await db.update_event(event.id, "time", time)
        elif field == "place":
            if not value:
                return await retry("Потрібен текст.")
            if len(value) > PLACE_MAX_LEN:
                return await retry(f"Задовго ({len(value)} символів, максимум {PLACE_MAX_LEN}).")
            await db.update_event(event.id, "place", value)
        elif field == "url":
            if not is_valid_url(value):
                return await retry("Це не схоже на посилання. Воно має починатися з https://")
            await db.update_event(event.id, "url", value)

        event = await db.get_event(event_id)
        if adding:
            return await next_step(message.bot, chat_id, p.settings_msg_id, p.user_id, event, field, db, config)
        await edit_screen(message.bot, chat_id, p.settings_msg_id, await event_screen(db, config, event, SAVED[field]))

    return router
