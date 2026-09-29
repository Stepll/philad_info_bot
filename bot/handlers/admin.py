from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from bot.db import Database
from bot.render import send_section
from bot.sections import SECTIONS

HELP_TEXT = """<b>Керування контентом</b>

Розділи: {sections}

<b>Як оновити розділ</b>
Надішліть у цю групу повідомлення (фото з підписом або просто текст), а потім <b>дайте на нього відповідь (reply)</b> командою:

/set <code>розділ</code> — замінити фото і текст повністю
/set_text <code>розділ</code> — замінити лише текст (фото лишиться)
/set_photo <code>розділ</code> — замінити лише фото (текст лишиться)

Текст можна також написати одразу після команди:
<code>/set_text events Текст оголошення…</code>

/del_photo <code>розділ</code> — прибрати фото
/reset <code>розділ</code> — повернути стандартний текст і прибрати фото
/show <code>розділ</code> — подивитися, як бачать користувачі
/sections — список розділів
/chat_id — ID цього чату

Форматування (жирний, курсив, посилання) зберігається."""


def _sections_list() -> str:
    return "\n".join(f"• <code>{s.key}</code> — {s.title}" for s in SECTIONS.values())


def _parse_key(command: CommandObject) -> tuple[str | None, str | None]:
    """Повертає (ключ розділу, решту тексту після ключа)."""
    if not command.args:
        return None, None
    parts = command.args.split(maxsplit=1)
    key = parts[0].lower()
    if key not in SECTIONS:
        return None, None
    return key, parts[1] if len(parts) > 1 else None


async def _require_key(message: Message, command: CommandObject) -> str | None:
    key, _ = _parse_key(command)
    if key is None:
        await message.reply(
            f"Вкажіть розділ: /{command.command} <code>розділ</code>\n\n{_sections_list()}"
        )
    return key


def _inline_html_text(message: Message) -> str | None:
    """Текст після `/команда розділ` зі збереженням форматування."""
    parts = message.html_text.split(maxsplit=2)
    return parts[2] if len(parts) > 2 else None


def _reply_html_text(message: Message) -> str | None:
    reply = message.reply_to_message
    if reply and (reply.text or reply.caption):
        return reply.html_text
    return None


def _reply_photo_id(message: Message) -> str | None:
    reply = message.reply_to_message
    if reply and reply.photo:
        return reply.photo[-1].file_id
    return None


def create_router(admin_chat_id: int) -> Router:
    router = Router(name="admin")
    router.message.filter(F.chat.id == admin_chat_id)

    @router.message(Command("help", "start"))
    async def cmd_help(message: Message) -> None:
        await message.answer(HELP_TEXT.format(sections=", ".join(SECTIONS)))

    @router.message(Command("sections"))
    async def cmd_sections(message: Message) -> None:
        await message.answer(_sections_list())

    @router.message(Command("show"))
    async def cmd_show(message: Message, command: CommandObject, db: Database) -> None:
        if key := await _require_key(message, command):
            await send_section(message.bot, message.chat.id, db, key)

    @router.message(Command("set"))
    async def cmd_set(message: Message, command: CommandObject, db: Database) -> None:
        if not (key := await _require_key(message, command)):
            return
        text = _reply_html_text(message)
        photo_id = _reply_photo_id(message)
        if text is None and photo_id is None:
            await message.reply("Дайте цією командою відповідь на повідомлення з фото та/або текстом.")
            return
        await db.set_text(key, text, message.from_user.id)
        await db.set_photo(key, photo_id, message.from_user.id)
        await _done(message, db, key)

    @router.message(Command("set_text"))
    async def cmd_set_text(message: Message, command: CommandObject, db: Database) -> None:
        if not (key := await _require_key(message, command)):
            return
        text = _inline_html_text(message) or _reply_html_text(message)
        if not text:
            await message.reply(
                "Напишіть текст після команди або дайте командою відповідь на повідомлення з текстом."
            )
            return
        await db.set_text(key, text, message.from_user.id)
        await _done(message, db, key)

    @router.message(Command("set_photo"))
    async def cmd_set_photo(message: Message, command: CommandObject, db: Database) -> None:
        if not (key := await _require_key(message, command)):
            return
        photo_id = _reply_photo_id(message)
        if not photo_id:
            await message.reply("Дайте цією командою відповідь на повідомлення з фото.")
            return
        await db.set_photo(key, photo_id, message.from_user.id)
        await _done(message, db, key)

    @router.message(Command("del_photo"))
    async def cmd_del_photo(message: Message, command: CommandObject, db: Database) -> None:
        if key := await _require_key(message, command):
            await db.set_photo(key, None, message.from_user.id)
            await _done(message, db, key)

    @router.message(Command("reset"))
    async def cmd_reset(message: Message, command: CommandObject, db: Database) -> None:
        if key := await _require_key(message, command):
            await db.set_text(key, None, message.from_user.id)
            await db.set_photo(key, None, message.from_user.id)
            await _done(message, db, key)

    return router


async def _done(message: Message, db: Database, key: str) -> None:
    await message.reply(f"✅ Розділ «{SECTIONS[key].title}» оновлено. Так його бачать користувачі:")
    await send_section(message.bot, message.chat.id, db, key)


# Працює в будь-якому чаті — щоб дізнатися ID групи адмінів при налаштуванні
common_router = Router(name="common")


@common_router.message(Command("chat_id"))
async def cmd_chat_id(message: Message) -> None:
    await message.reply(f"ID цього чату: <code>{message.chat.id}</code>")
