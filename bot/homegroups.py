"""Домашні групи: окремі сторінки для слайдера «Вибрати домашку»."""

from dataclasses import dataclass

from bot.events import html_to_plain

# Підпис під фото — до 1024 символів у Telegram
TEXT_LIMIT = 900


@dataclass
class HomeGroup:
    id: int
    photo_id: str
    text: str  # HTML
    leader: str | None  # @username без «@»

    @property
    def title(self) -> str:
        """Перший рядок тексту — назва групи (для списку в адмінці)."""
        first = html_to_plain(self.text).strip().split("\n", 1)[0].strip()
        return first or "Домашня група"
