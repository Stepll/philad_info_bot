from dataclasses import dataclass


@dataclass(frozen=True)
class Section:
    key: str
    title: str
    default_text: str
    # False — вміст розділу не редагується командами /set (напр. «Давай знайомитись» — лише посилання)
    has_content: bool = True


_PLACEHOLDER = "Інформація незабаром з'явиться 🙏"

SECTIONS: dict[str, Section] = {
    s.key: s
    for s in (
        Section(
            "welcome",
            "👋 Привітання",
            "Вітаємо! Тут ви знайдете всю актуальну інформацію нашої церкви.\n\n"
            "Оберіть розділ нижче 👇",
        ),
        Section("events", "📅 Події", _PLACEHOLDER),
        Section("homegroups", "🏠 Домашні групи", _PLACEHOLDER),
        Section("schedule", "🕐 Розклад", _PLACEHOLDER),
        Section("serving", "🙌 Потреба в служінні", _PLACEHOLDER),
        Section("donations", "💛 Пожертвування", _PLACEHOLDER),
        Section("meet", "🤝 Давай знайомитись", "", has_content=False),
    )
}

# Кнопки головного меню (welcome показується на /start, а не як кнопка)
MENU_SECTIONS = ["events", "homegroups", "schedule", "serving", "donations", "meet"]

CONTENT_SECTIONS = [key for key, s in SECTIONS.items() if s.has_content]
