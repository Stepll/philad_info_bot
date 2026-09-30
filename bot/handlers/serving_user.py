"""«Потреба в служінні» для людей: список → опис → «Хочу долучитися» (все в одному повідомленні)."""

import logging
from contextlib import suppress
from html import escape

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.filters.callback_data import CallbackData
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message, User
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.config import Config
from bot.db import Database
from bot.keyboards import main_menu_kb
from bot.sections import SECTIONS
from bot.serving import Need

log = logging.getLogger(__name__)

HEADER = f"<b>{SECTIONS['serving'].title}</b>\n\n"
NO_NEEDS = "Зараз відкритих потреб немає 🙏"


class NeedNav(CallbackData, prefix="svu"):
    action: str  # list | open | join
    need: int = 0


def list_view(needs: list[Need]) -> tuple[str, InlineKeyboardMarkup]:
    kb = InlineKeyboardBuilder()
    for need in needs:
        kb.button(text=need.title, callback_data=NeedNav(action="open", need=need.id))
    kb.adjust(1)
    return HEADER + "Оберіть, де хотіли б послужити 👇", kb.as_markup()


def need_view(need: Need, joined: bool) -> tuple[str, InlineKeyboardMarkup]:
    kb = InlineKeyboardBuilder()
    kb.button(
        text="✅ Ви відгукнулися" if joined else "🙋 Хочу долучитися",
        callback_data=NeedNav(action="join", need=need.id),
    )
    kb.button(text="⬅️ Назад", callback_data=NeedNav(action="list"))
    kb.adjust(1)
    text = f"<b>{escape(need.title)}</b>\n\n{need.description or need.summary}"
    if joined:
        text += "\n\n<i>Дякуємо! З вами зв'яжуться 🙏</i>"
    return text, kb.as_markup()


def _person(user: User) -> str:
    name = f'<a href="tg://user?id={user.id}">{escape(user.full_name)}</a>'
    return f"{name} · @{user.username}" if user.username else name


async def notify(bot: Bot, db: Database, config: Config, need: Need, user: User) -> None:
    """Відгук — у групу адмінів і особисто відповідальному (якщо бот його знає)."""
    text = f"🙋 <b>Новий відгук:</b> {escape(need.title)}\n{_person(user)}"

    note = ""
    if need.responsible:
        responsible_id = await db.find_user_id(need.responsible)
        delivered = False
        if responsible_id:
            try:
                await bot.send_message(responsible_id, text)
                delivered = True
            except (TelegramForbiddenError, TelegramBadRequest):
                log.warning("Не вдалося написати відповідальному @%s", need.responsible)
        note = f"\nВідповідальний: @{escape(need.responsible)}"
        if not delivered:
            note += " (особисто не сповіщено — хай надішле боту /start)"

    if config.admin_chat_id:
        await bot.send_message(config.admin_chat_id, text + note)


router = Router(name="serving_user")
router.message.filter(F.chat.type == "private")
router.callback_query.filter(F.message.chat.type == "private")


@router.message(F.text == SECTIONS["serving"].title)
async def on_serving(message: Message, db: Database) -> None:
    needs = await db.list_needs()
    if not needs:
        await message.answer(NO_NEEDS, reply_markup=main_menu_kb())
        return
    text, markup = list_view(needs)
    await message.answer(text, reply_markup=markup)


async def _edit(callback: CallbackQuery, view: tuple[str, InlineKeyboardMarkup]) -> None:
    text, markup = view
    with suppress(TelegramBadRequest):
        await callback.message.edit_text(text, reply_markup=markup)


async def _show_list(callback: CallbackQuery, db: Database) -> None:
    needs = await db.list_needs()
    if not needs:
        with suppress(TelegramBadRequest):
            await callback.message.edit_text(NO_NEEDS)
        return
    await _edit(callback, list_view(needs))


@router.callback_query(NeedNav.filter(F.action == "list"))
async def on_list(callback: CallbackQuery, db: Database) -> None:
    await callback.answer()
    await _show_list(callback, db)


@router.callback_query(NeedNav.filter(F.action.in_({"open", "join"})))
async def on_need(callback: CallbackQuery, callback_data: NeedNav, db: Database, config: Config) -> None:
    need = await db.get_need(callback_data.need)
    if not need:
        await callback.answer("Ця потреба вже неактуальна", show_alert=True)
        return await _show_list(callback, db)

    user = callback.from_user
    if callback_data.action == "join":
        if await db.add_response(user.id, need.id):
            await notify(callback.bot, db, config, need, user)
            await callback.answer("Дякуємо! Ми передали ваш відгук 🙏")
        else:
            await callback.answer("Ви вже відгукнулися — з вами зв'яжуться 🙏", show_alert=True)
    else:
        await callback.answer()

    await _edit(callback, need_view(need, await db.has_response(user.id, need.id)))
