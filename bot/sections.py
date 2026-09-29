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
        # Події — постери з гортанням, редагуються в /settings
        Section("events", "📅 Події", "", has_content=False),
        Section("homegroups", "🏠 Домашні групи", _PLACEHOLDER),
        # Розклад — згенерована картинка, редагується блоками в /settings
        Section("schedule", "🕐 Розклад", "", has_content=False),
        # Потреба в служінні — список потреб з відгуками, редагується в /settings
        Section("serving", "🙌 Потреба в служінні", "", has_content=False),
        Section("donations", "💛 Пожертвування", _PLACEHOLDER),
        Section("meet", "🤝 Давай знайомитись", "", has_content=False),
    )
}

# Кнопки головного меню (welcome показується на /start, а не як кнопка)
MENU_SECTIONS = ["events", "homegroups", "schedule", "serving", "donations", "meet"]

CONTENT_SECTIONS = [key for key, s in SECTIONS.items() if s.has_content]
