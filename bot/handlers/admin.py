from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message

HELP_TEXT = """<b>Керування ботом</b>

/settings — меню налаштувань. Оберіть розділ і змінюйте його кнопками:

• <b>👋 Привітання</b> — фото і текст, які бачать на старті
• <b>📅 Події</b> — постери, дата, час, місце, посилання
• <b>🏠 Домашні групи</b>, <b>💛 Пожертвування</b>, <b>🌐 Соцмережі</b> — фото, текст, посилання
• <b>🕐 Розклад</b> — блоки розкладу (з них генерується картинка)
• <b>🙌 Потреба в служінні</b> — потреби і відповідальні
• <b>🙏 Потреби</b> — посилання на інший бот
• <b>🤝 Давай знайомитись</b> — посилання на форму

Коли бот просить щось надіслати — <b>дайте відповідь (reply) на його повідомлення</b>. Зайві повідомлення бот прибере сам.

Сюди ж приходять відгуки на потреби в служінні."""


def create_router(admin_chat_id: int) -> Router:
    router = Router(name="admin")
    router.message.filter(F.chat.id == admin_chat_id)

    @router.message(Command("help"))
    async def cmd_help(message: Message) -> None:
        await message.answer(HELP_TEXT)

    return router


# Лише поки ADMIN_CHAT_ID не задано — щоб дізнатися ID групи адмінів при налаштуванні
setup_router = Router(name="setup")


@setup_router.message(Command("chat_id"))
async def cmd_chat_id(message: Message) -> None:
    await message.reply(f"ID цього чату: <code>{message.chat.id}</code>")
