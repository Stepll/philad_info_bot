"""Потреба в служінні: модель і перевірка введення."""

import re
from dataclasses import dataclass

TITLE_MAX_LEN = 40  # назва — це ще й текст кнопки
SUMMARY_MAX_LEN = 150
DESCRIPTION_MAX_LEN = 3000


@dataclass
class Need:
    id: int
    title: str
    summary: str  # HTML, рядок у загальному списку
    description: str  # HTML, повний опис
    responsible: str | None  # @username без «@»


def parse_username(value: str) -> str | None:
    """'@ivan', 'ivan', 't.me/ivan', 'https://t.me/ivan' -> 'ivan'."""
    value = value.strip()
    value = re.sub(r"^(https?://)?(t\.me|telegram\.me)/", "", value).lstrip("@")
    return value if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{3,31}", value) else None
