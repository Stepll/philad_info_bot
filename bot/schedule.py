import re
from dataclasses import dataclass

DAYS_SHORT = ["ПН", "ВТ", "СР", "ЧТ", "ПТ", "СБ", "НД"]
DAYS_FULL = ["Понеділок", "Вівторок", "Середа", "Четвер", "П'ятниця", "Субота", "Неділя"]


@dataclass(frozen=True)
class Color:
    name: str
    emoji: str
    bg: str
    fg: str


COLORS: dict[str, Color] = {
    "white": Color("Білий", "⬜", "#FFFFFF", "#1C1C1E"),
    "navy": Color("Синій", "🟦", "#15355A", "#FFFFFF"),
    "teal": Color("Бірюзовий", "🩵", "#2A8FA5", "#FFFFFF"),
    "crimson": Color("Бордовий", "🟥", "#8A2442", "#FFFFFF"),
    "green": Color("Зелений", "🟩", "#23622E", "#FFFFFF"),
    "purple": Color("Фіолетовий", "🟪", "#5B3A8C", "#FFFFFF"),
    "orange": Color("Помаранчевий", "🟧", "#C0662A", "#FFFFFF"),
}
DEFAULT_COLOR = "white"

TITLE_MAX_LEN = 40


@dataclass
class ScheduleItem:
    id: int
    day: int  # 0 = понеділок
    time: str  # "H:MM"
    title: str
    color: str

    @property
    def minutes(self) -> int:
        h, m = self.time.split(":")
        return int(h) * 60 + int(m)


def parse_time(value: str) -> str | None:
    """'7:30', '07.30', '19 00' -> '7:30' / '19:00'; None, якщо формат невірний."""
    match = re.fullmatch(r"\s*(\d{1,2})\s*[:.\s]\s*(\d{2})\s*", value)
    if not match:
        return None
    h, m = int(match[1]), int(match[2])
    if h > 23 or m > 59:
        return None
    return f"{h}:{m:02d}"


# Стартовий розклад (заповнюється один раз, при першому запуску)
SEED: list[tuple[int, str, str, str]] = [
    (0, "19:00", "Молитва", "white"),
    (1, "7:30", "Ранкова молитва", "white"),
    (1, "11:00", "Група по вивченню Біблії", "navy"),
    (2, "19:00", "Вечірнє служіння", "navy"),
    (3, "8:00", "Ранкова молитва", "white"),
    (5, "17:00", "Молодіжне служіння", "green"),
    (6, "10:00", "Ранкова молитва", "white"),
    (6, "11:00", "Недільне зібрання", "teal"),
    (6, "11:00", "Недільна школа", "crimson"),
]
