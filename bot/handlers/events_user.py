"""Розділ «Події» для користувачів: постери з гортанням в одному повідомленні + календар."""

from contextlib import suppress
from datetime import timedelta
from html import escape

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
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

from bot.config import Config
from bot.db import Database
from bot.events import KEEP_PAST_DAYS, Event, build_ics, caption, google_calendar_url, ics_filename
from bot.keyboards import main_menu_kb
from bot.sections import SECTIONS
from bot.web import calendar_url

NO_EVENTS = "Найближчих подій поки немає 🙏"


class EventNav(CallbackData, prefix="evu"):
    action: str  # show | cal | noop
    event: int = 0


def event_kb(events: list[Event], index: int, in_calendar: bool) -> InlineKeyboardMarkup:
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
    kb.button(
        text="✅ У календарі" if in_calendar else "📅 Додати в календар",
        callback_data=EventNav(action="cal", event=event.id),
    )
    sizes.append(1)
    kb.adjust(*sizes)
    return kb.as_markup()


async def _upcoming(db: Database, config: Config) -> list[Event]:
    today = config.today()
    await db.purge_events_before(today - timedelta(days=KEEP_PAST_DAYS))
    return await db.upcoming_events(today)


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
    await message.answer_photo(first.poster_id, caption=caption(first), reply_markup=event_kb(events, 0, in_cal))


@router.callback_query(EventNav.filter(F.action == "noop"))
async def on_noop(callback: CallbackQuery) -> None:
    await callback.answer()


@router.callback_query(EventNav.filter(F.action == "show"))
async def on_show(callback: CallbackQuery, callback_data: EventNav, db: Database, config: Config) -> None:
    events = await _upcoming(db, config)
    if not events:
        await callback.answer(NO_EVENTS, show_alert=True)
        with suppress(TelegramBadRequest):
            await callback.message.delete()
        return

    ids = [e.id for e in events]
    index = ids.index(callback_data.event) if callback_data.event in ids else 0
    event = events[index]
    in_cal = await db.is_in_calendar(callback.from_user.id, event.id)
    await callback.answer()
    with suppress(TelegramBadRequest):
        await callback.message.edit_media(
            InputMediaPhoto(media=event.poster_id, caption=caption(event)),
            reply_markup=event_kb(events, index, in_cal),
        )


@router.callback_query(EventNav.filter(F.action == "cal"))
async def on_calendar(callback: CallbackQuery, callback_data: EventNav, db: Database, config: Config) -> None:
    event = await db.get_event(callback_data.event)
    if not event or not event.day or event.day < config.today():
        await callback.answer("Ця подія вже неактуальна", show_alert=True)
        return

    await callback.answer()
    await db.mark_in_calendar(callback.from_user.id, event.id)

    title = f"📅 <b>{escape(event.title)}</b>\n\n"
    google = InlineKeyboardButton(text="📆 Android / Google Calendar", url=google_calendar_url(event))
    if config.public_url:
        # iPhone додає подію, лише якщо .ics відкрито в браузері — тому посилання на наш сервер
        await callback.message.answer(
            title + "Оберіть свій календар 👇\n\n"
            "<i>На iPhone сторінка відкриється в браузері Telegram — натисніть на ній «Відкрити в Safari», "
            "а потім «Додати в календар».</i>",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="🍏 iPhone / Apple Calendar", url=calendar_url(config, event))],
                    [google],
                ]
            ),
        )
    else:
        await callback.message.answer_document(
            BufferedInputFile(build_ics(event), filename=ics_filename(event)),
            caption=title + "Відкрийте файл, щоб додати подію в календар телефону.\n"
            "Якщо файл не відкривається — скористайтеся Google Calendar 👇",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[google]]),
        )

    # Оновлюємо кнопку на постері: «✅ У календарі»
    events = await _upcoming(db, config)
    ids = [e.id for e in events]
    if event.id in ids:
        with suppress(TelegramBadRequest):
            await callback.message.edit_reply_markup(reply_markup=event_kb(events, ids.index(event.id), True))
