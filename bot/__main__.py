import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommandScopeAllPrivateChats, BotCommandScopeChat, BotCommandScopeDefault

from bot.config import load_config
from bot.db import Database
from bot.handlers import (
    admin,
    admin_events,
    admin_schedule,
    admin_serving,
    admin_settings,
    events_user,
    serving_user,
    user,
)
from bot.middlewares import RememberUsers
from bot.web import start_web


async def clear_commands(bot: Bot, admin_chat_id: int) -> None:
    """Прибирає підказки команд скрізь: люди користуються кнопками, адміни — /help і /settings."""
    await bot.delete_my_commands(scope=BotCommandScopeDefault())
    await bot.delete_my_commands(scope=BotCommandScopeAllPrivateChats())
    if admin_chat_id:
        await bot.delete_my_commands(scope=BotCommandScopeChat(chat_id=admin_chat_id))


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    config = load_config()

    db = Database(config.db_path)
    await db.init()

    bot = Bot(config.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    dp["db"] = db
    dp["config"] = config
    remember_users = RememberUsers(db)
    dp.message.outer_middleware(remember_users)
    dp.callback_query.outer_middleware(remember_users)

    # Порядок важливий: адмін-команди — раніше за обробник введення в /settings,
    # щоб команда посеред введення посилання спрацювала як команда.
    if not config.admin_chat_id:
        dp.include_router(admin.setup_router)  # /chat_id — лише для першого налаштування
    dp.include_routers(
        admin.create_router(config.admin_chat_id),
        admin_settings.create_router(config.admin_chat_id),
        admin_schedule.create_router(config.admin_chat_id),
        admin_events.create_router(config.admin_chat_id),
        admin_serving.create_router(config.admin_chat_id),
        events_user.router,
        serving_user.router,
        user.router,
    )

    await clear_commands(bot, config.admin_chat_id)
    await bot.delete_webhook(drop_pending_updates=True)

    web_runner = None
    if config.public_url:
        # Помилка вебсервера (напр. зайнятий порт) не повинна зупиняти бота
        try:
            web_runner = await start_web(bot, db, config)
        except OSError:
            logging.exception(
                "Не вдалося запустити вебсервер на %s:%s — календарні посилання не працюватимуть",
                config.web_host, config.web_port,
            )
    try:
        await dp.start_polling(bot)
    finally:
        if web_runner:
            await web_runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
