import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, BotCommandScopeAllPrivateChats, BotCommandScopeChat

from bot.config import load_config
from bot.db import Database
from bot.handlers import admin, form, user


async def set_commands(bot: Bot, admin_chat_id: int) -> None:
    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Головне меню"),
            BotCommand(command="menu", description="Головне меню"),
        ],
        scope=BotCommandScopeAllPrivateChats(),
    )
    if admin_chat_id:
        await bot.set_my_commands(
            [
                BotCommand(command="help", description="Як керувати контентом"),
                BotCommand(command="set", description="Замінити фото і текст (reply)"),
                BotCommand(command="set_text", description="Замінити текст"),
                BotCommand(command="set_photo", description="Замінити фото (reply)"),
                BotCommand(command="del_photo", description="Прибрати фото"),
                BotCommand(command="reset", description="Повернути стандартний вміст"),
                BotCommand(command="show", description="Переглянути розділ"),
                BotCommand(command="sections", description="Список розділів"),
            ],
            scope=BotCommandScopeChat(chat_id=admin_chat_id),
        )


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    config = load_config()

    db = Database(config.db_path)
    await db.init()

    bot = Bot(config.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    dp["db"] = db
    dp["config"] = config

    # Порядок важливий: user.router має fallback, тому form.router — після нього,
    # а fallback обмежено станом None, щоб не перехоплювати відповіді в анкеті.
    dp.include_routers(
        admin.common_router,
        admin.create_router(config.admin_chat_id),
        user.router,
        form.router,
    )

    await set_commands(bot, config.admin_chat_id)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
