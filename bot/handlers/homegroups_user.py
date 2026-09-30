"""«Домашні групи» для людей: загальний опис → «Вибрати домашку» → слайдер груп (одне повідомлення)."""

from contextlib import suppress

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters.callback_data import CallbackData
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InputMediaPhoto, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.db import Database
from bot.homegroups import HomeGroup
from bot.render import CAPTION_LIMIT, send_section
from bot.sections import SECTIONS
from bot.settings import HOMEGROUPS_URL, SECTION_URL_BUTTONS


class GroupNav(CallbackData, prefix="hgu"):
    action: str  # show | back | noop
    group: int = 0


async def overview_kb(db: Database) -> InlineKeyboardMarkup | None:
    """Кнопки під загальним описом: посилання розділу (якщо є) і «Вибрати домашку» (якщо є групи)."""
    kb = InlineKeyboardBuilder()
    url = await db.get_setting(HOMEGROUPS_URL)
    if url:
        kb.button(text=SECTION_URL_BUTTONS["homegroups"], url=url)
    groups = await db.list_groups()
    if groups:
        kb.button(text="👥 Вибрати домашку", callback_data=GroupNav(action="show", group=groups[0].id))
    kb.adjust(1)
    return kb.as_markup() if (url or groups) else None


def group_kb(groups: list[HomeGroup], index: int) -> InlineKeyboardMarkup:
    group = groups[index]
    kb = InlineKeyboardBuilder()
    sizes = []
    if group.leader:
        kb.button(text="✉️ Написати лідеру", url=f"https://t.me/{group.leader}")
        sizes.append(1)
    kb.button(text="⬅️ Назад", callback_data=GroupNav(action="back"))
    sizes.append(1)
    # Гортання — в самому низу, як у подіях
    if len(groups) > 1:
        kb.button(text="◀️", callback_data=GroupNav(action="show", group=groups[index - 1].id))
        kb.button(text=f"{index + 1} / {len(groups)}", callback_data=GroupNav(action="noop"))
        kb.button(text="▶️", callback_data=GroupNav(action="show", group=groups[(index + 1) % len(groups)].id))
        sizes.append(3)
    kb.adjust(*sizes)
    return kb.as_markup()


router = Router(name="homegroups_user")
router.message.filter(F.chat.type == "private")
router.callback_query.filter(F.message.chat.type == "private")


@router.message(F.text == SECTIONS["homegroups"].title)
async def on_homegroups(message: Message, db: Database) -> None:
    await send_section(message.bot, message.chat.id, db, "homegroups", await overview_kb(db))


@router.callback_query(GroupNav.filter(F.action == "noop"))
async def on_noop(callback: CallbackQuery) -> None:
    await callback.answer()


@router.callback_query(GroupNav.filter(F.action == "show"))
async def on_show(callback: CallbackQuery, callback_data: GroupNav, db: Database) -> None:
    groups = await db.list_groups()
    if not groups:
        await callback.answer("Список груп поки порожній 🙏", show_alert=True)
        return
    ids = [g.id for g in groups]
    index = ids.index(callback_data.group) if callback_data.group in ids else 0
    group = groups[index]
    await callback.answer()

    media = InputMediaPhoto(media=group.photo_id, caption=group.text or None)
    markup = group_kb(groups, index)
    if callback.message.photo:
        with suppress(TelegramBadRequest):
            await callback.message.edit_media(media, reply_markup=markup)
    else:
        # Текстове повідомлення не можна перетворити на фото — замінюємо новим
        with suppress(TelegramBadRequest):
            await callback.message.delete()
        await callback.message.answer_photo(group.photo_id, caption=group.text or None, reply_markup=markup)


@router.callback_query(GroupNav.filter(F.action == "back"))
async def on_back(callback: CallbackQuery, db: Database) -> None:
    await callback.answer()
    content = await db.get_section("homegroups")
    markup = await overview_kb(db)
    if content.photo_id and len(content.text) <= CAPTION_LIMIT:
        with suppress(TelegramBadRequest):
            await callback.message.edit_media(
                InputMediaPhoto(media=content.photo_id, caption=content.text or None), reply_markup=markup
            )
        return
    # Загальний опис без фото (або з задовгим текстом) — надсилаємо його заново
    with suppress(TelegramBadRequest):
        await callback.message.delete()
    await send_section(callback.bot, callback.message.chat.id, db, "homegroups", markup)
