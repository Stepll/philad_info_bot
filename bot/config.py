import logging
import os
from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Config:
    bot_token: str
    admin_chat_id: int  # 0 = ще не налаштовано
    db_path: str
    timezone: str  # для визначення «сьогодні» (які події вже минули)
    # Публічна адреса бота (https://…), з якої iPhone відкриває .ics. Порожньо — вебсервер вимкнено
    public_url: str
    web_host: str
    web_port: int

    def today(self) -> date:
        return datetime.now(ZoneInfo(self.timezone)).date()


def load_config() -> Config:
    load_dotenv()

    token = os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError("BOT_TOKEN не задано (див. .env.example)")

    admin_chat_id = int(os.getenv("ADMIN_CHAT_ID") or 0)
    if not admin_chat_id:
        log.warning(
            "ADMIN_CHAT_ID не задано — адмін-команди вимкнені. "
            "Додайте бота в групу адмінів і надішліть /chat_id"
        )

    return Config(
        bot_token=token,
        admin_chat_id=admin_chat_id,
        db_path=os.getenv("DB_PATH", "data/bot.db"),
        timezone=os.getenv("TIMEZONE", "Europe/Kyiv"),
        public_url=os.getenv("PUBLIC_URL", "").rstrip("/"),
        web_host=os.getenv("WEB_HOST", "127.0.0.1"),
        web_port=int(os.getenv("WEB_PORT") or 8080),
    )
