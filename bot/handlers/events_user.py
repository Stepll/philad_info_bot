"""Розділ «Події» для користувачів: постери з гортанням в одному повідомленні + календар."""

import logging
from contextlib import suppress
from datetime import timedelta
from html import escape

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.filters.callback_data import CallbackData
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    Message,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.cal_links import carousel_calendar_url
from bot.config import Config
from bot.db import Database
from bot.events import KEEP_PAST_DAYS, Event, build_ics, caption, google_calendar_url, ics_filename
from bot.keyboards import main_menu_kb
from bot.sections import SECTIONS

log = logging.getLogger(__name__)

NO_EVENTS = "Найближчих подій поки немає 🙏"

# Яку подію зараз показує кожен постер: (chat_id, message_id) -> event_id.
# Потрібно, щоб сервер оновив кнопку «✅ У календарі» лише якщо людина ще на тій самій події.
_shown: dict[tuple[int, int], int] = {}


class EventNav(CallbackData, prefix="evu"):
    action: str  # show | cal | noop
    event: int = 0


def event_kb(
    events: list[Event], index: int, in_calendar: bool, config: Config, chat_id: int = 0, message_id: int = 0
) -> InlineKeyboardMarkup:
    event = events[index]
    kb = InlineKeyboardBuilder()
    sizes = []
    if len(events) > 1:
        prev_id = events[index - 1].id
        next_id = events[(index + 1) % len(events)].id
        kb.button(text="◀️", callback_data=EventNav(action="show", event=prev_id))
        kb.button(text=f"{index + 1} / {len(events)}", callback_data=EventNav(action="noop"))
        kb.button(text="▶️", callback_data=EventNav(action="show", event=next_id))
        sizes.append(3)
    if event.url:
        kb.button(text="🔗 Детальніше", url=event.url)
        sizes.append(1)

    label = "✅ У календарі" if in_calendar else "📅 Додати в календар"
    if config.public_url and message_id:
        # Одразу на сторінку події; відмітку «✅» ставить сервер, коли сторінку відкрито
        kb.button(text=label, url=carousel_calendar_url(config, event.id, chat_id, message_id))
    else:
        kb.button(text=label, callback_data=EventNav(action="cal", event=event.id))
    sizes.append(1)
    kb.adjust(*sizes)
    return kb.as_markup()


async def _upcoming(db: Database, config: Config) -> list[Event]:
    today = config.today()
    await db.purge_events_before(today - timedelta(days=KEEP_PAST_DAYS))
    return await db.upcoming_events(today)


async def mark_opened(bot: Bot, db: Database, config: Config, chat_id: int, message_id: int, event_id: int) -> None:
    """Сервер: людина відкрила сторінку події з постера — ставимо «✅ У календарі»."""
    await db.mark_in_calendar(chat_id, event_id)  # в особистому чаті chat_id == user_id
    if _shown.get((chat_id, message_id)) != event_id:
        return  # постер уже показує іншу подію або бот перезапускався — кнопка оновиться при гортанні
    events = await _upcoming(db, config)
    ids = [e.id for e in events]
    if event_id not in ids:
        return
    markup = event_kb(events, ids.index(event_id), True, config, chat_id, message_id)
    with suppress(TelegramAPIError):
        await bot.edit_message_reply_markup(chat_id=chat_id, message_id=message_id, reply_markup=markup)


router = Router(name="events_user")
router.message.filter(F.chat.type == "private")
router.callback_query.filter(F.message.chat.type == "private")


@router.message(F.text == SECTIONS["events"].title)
async def on_events(message: Message, db: Database, config: Config) -> None:
    events = await _upcoming(db, config)
    if not events:
        await message.answer(NO_EVENTS, reply_markup=main_menu_kb())
        return
    first = events[0]
    in_cal = await db.is_in_calendar(message.from_user.id, first.id)
    sent = await message.answer_photo(
        first.poster_id, caption=caption(first), reply_markup=event_kb(events, 0, in_cal, config)
    )
    _shown[(sent.chat.id, sent.message_id)] = first.id
    if config.public_url:
        # Посилання календаря містить id цього повідомлення — тож кнопку з ним ставимо слідом
        with suppress(TelegramBadRequest):
            await message.bot.edit_message_reply_markup(
                chat_id=sent.chat.id,
                message_id=sent.message_id,
                reply_markup=event_kb(events, 0, in_cal, config, sent.chat.id, sent.message_id),
            )


@router.callback_query(EventNav.filter(F.action == "noop"))
async def on_noop(callback: CallbackQuery) -> None:
    await callback.answer()


async def _show(callback: CallbackQuery, db: Database, config: Config, event_id: int) -> None:
    events = await _upcoming(db, config)
    if not events:
        await callback.answer(NO_EVENTS, show_alert=True)
        with suppress(TelegramBadRequest):
            await callback.message.delete()
        return

    ids = [e.id for e in events]
    index = ids.index(event_id) if event_id in ids else 0
    event = events[index]
    in_cal = await db.is_in_calendar(callback.from_user.id, event.id)
    await callback.answer()
    chat_id, message_id = callback.message.chat.id, callback.message.message_id
    _shown[(chat_id, message_id)] = event.id
    with suppress(TelegramBadRequest):
        await callback.message.edit_media(
            InputMediaPhoto(media=event.poster_id, caption=caption(event)),
            reply_markup=event_kb(events, index, in_cal, config, chat_id, message_id),
        )


@router.callback_query(EventNav.filter(F.action == "show"))
async def on_show(callback: CallbackQuery, callback_data: EventNav, db: Database, config: Config) -> None:
    await _show(callback, db, config, callback_data.event)


@router.callback_query(EventNav.filter(F.action == "cal"))
async def on_calendar(callback: CallbackQuery, callback_data: EventNav, db: Database, config: Config) -> None:
    """Кнопка-колбек: без PUBLIC_URL (надсилаємо .ics-файл) або на старих постерах."""
    event = await db.get_event(callback_data.event)
    if not event or not event.day or event.day < config.today():
        await callback.answer("Ця подія вже неактуальна", show_alert=True)
        return

    if config.public_url:
        # Старий постер — перемальовуємо з кнопкою-посиланням
        return await _show(callback, db, config, event.id)

    await callback.answer()
    await db.mark_in_calendar(callback.from_user.id, event.id)
    await callback.message.answer_document(
        BufferedInputFile(build_ics(event), filename=ics_filename(event)),
        caption=f"📅 <b>{escape(event.title)}</b>\n\n"
        "Відкрийте файл, щоб додати подію в календар телефону.\n"
        "Якщо файл не відкривається — скористайтеся Google Calendar 👇",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="📆 Google Calendar", url=google_calendar_url(event))]]
        ),
    )

    events = await _upcoming(db, config)
    ids = [e.id for e in events]
    if event.id in ids:
        with suppress(TelegramBadRequest):
            await callback.message.edit_reply_markup(reply_markup=event_kb(events, ids.index(event.id), True, config))
