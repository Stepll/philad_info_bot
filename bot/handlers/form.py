from contextlib import suppress
from html import escape

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove

from bot.config import Config
from bot.db import Database
from bot.keyboards import (
    SKIP_PHONE_TEXT,
    FormCb,
    form_cancel_kb,
    form_confirm_kb,
    form_skip_kb,
    main_menu_kb,
    phone_kb,
)
from bot.render import send_section

router = Router(name="form")
router.message.filter(F.chat.type == "private")

NOT_SPECIFIED = "—"


class MeetForm(StatesGroup):
    name = State()
    phone = State()
    about = State()
    confirm = State()


async def _ask_name(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(MeetForm.name)
    await message.answer("Як вас звати? ✍️", reply_markup=form_cancel_kb())


@router.callback_query(FormCb.filter(F.action.in_({"start", "restart"})))
async def form_start(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    with suppress(TelegramBadRequest):
        await callback.message.edit_reply_markup(reply_markup=None)
    await _ask_name(callback.message, state)


@router.callback_query(FormCb.filter(F.action == "cancel"))
async def form_cancel(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    await callback.answer("Скасовано")
    await state.clear()
    with suppress(TelegramBadRequest):
        await callback.message.delete()
    await callback.message.answer("Анкету скасовано.", reply_markup=ReplyKeyboardRemove())
    await send_section(callback.bot, callback.message.chat.id, db, "welcome", main_menu_kb())


@router.message(MeetForm.name, F.text)
async def form_name(message: Message, state: FSMContext) -> None:
    name = message.text.strip()[:100]
    await state.update_data(name=name)
    await state.set_state(MeetForm.phone)
    await message.answer(
        f"Приємно познайомитись, {escape(name)}! 😊\n\n"
        "Залиште, будь ласка, номер телефону — натисніть кнопку нижче або напишіть його.",
        reply_markup=phone_kb(),
    )


@router.message(MeetForm.phone, F.contact | F.text)
async def form_phone(message: Message, state: FSMContext) -> None:
    if message.contact:
        phone = message.contact.phone_number
    elif message.text == SKIP_PHONE_TEXT:
        phone = NOT_SPECIFIED
    else:
        phone = message.text.strip()[:30]

    await state.update_data(phone=phone)
    await state.set_state(MeetForm.about)
    await message.answer("Дякуємо!", reply_markup=ReplyKeyboardRemove())
    await message.answer(
        "Розкажіть трохи про себе: як дізналися про церкву, "
        "чи хотіли б долучитися до домашньої групи або служіння, "
        "чи є молитовні потреби тощо.",
        reply_markup=form_skip_kb(),
    )


async def _show_confirm(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    await state.set_state(MeetForm.confirm)
    await message.answer(
        "Перевірте, будь ласка:\n\n"
        f"<b>Ім'я:</b> {escape(data['name'])}\n"
        f"<b>Телефон:</b> {escape(data['phone'])}\n"
        f"<b>Про себе:</b> {escape(data['about'])}",
        reply_markup=form_confirm_kb(),
    )


@router.message(MeetForm.about, F.text)
async def form_about(message: Message, state: FSMContext) -> None:
    await state.update_data(about=message.text.strip()[:2000])
    await _show_confirm(message, state)


@router.callback_query(MeetForm.about, FormCb.filter(F.action == "skip"))
async def form_about_skip(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    with suppress(TelegramBadRequest):
        await callback.message.edit_reply_markup(reply_markup=None)
    await state.update_data(about=NOT_SPECIFIED)
    await _show_confirm(callback.message, state)


@router.callback_query(MeetForm.confirm, FormCb.filter(F.action == "send"))
async def form_send(callback: CallbackQuery, state: FSMContext, db: Database, config: Config) -> None:
    await callback.answer()
    data = await state.get_data()
    await state.clear()
    user = callback.from_user

    submission_id = await db.add_submission(
        user.id, user.username, data["name"], data["phone"], data["about"]
    )

    if config.admin_chat_id:
        contact = f"@{user.username}" if user.username else f'<a href="tg://user?id={user.id}">написати</a>'
        await callback.bot.send_message(
            config.admin_chat_id,
            f"🤝 <b>Нова анкета «Давай знайомитись»</b> #{submission_id}\n\n"
            f"<b>Ім'я:</b> {escape(data['name'])}\n"
            f"<b>Телефон:</b> {escape(data['phone'])}\n"
            f"<b>Telegram:</b> {contact}\n"
            f"<b>Про себе:</b> {escape(data['about'])}",
        )

    with suppress(TelegramBadRequest):
        await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("Дякуємо! 🙏 Ми з вами зв'яжемося найближчим часом.")
    await send_section(callback.bot, callback.message.chat.id, db, "welcome", main_menu_kb())


@router.message(StateFilter(MeetForm))
async def form_unexpected(message: Message) -> None:
    await message.answer("Будь ласка, дайте відповідь текстом або скористайтеся кнопками 🙂")
