from dataclasses import dataclass


@dataclass(frozen=True)
class Section:
    key: str
    title: str
    default_text: str


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
        Section("events", "📅 Події", ""),
        Section("homegroups", "🏠 Домашні групи", _PLACEHOLDER),
        # Розклад — згенерована картинка, редагується блоками в /settings
        Section("schedule", "🕐 Розклад", ""),
        # Потреба в служінні — список потреб з відгуками, редагується в /settings
        Section("serving", "🙌 Потреба в служінні", ""),
        Section("donations", "💛 Пожертвування", _PLACEHOLDER),
        Section("socials", "🌐 Соцмережі", _PLACEHOLDER),
        Section("meet", "🤝 Давай знайомитись", ""),
    )
}

# Кнопки головного меню (welcome показується на /start, а не як кнопка)
MENU_SECTIONS = ["events", "homegroups", "schedule", "serving", "donations", "socials", "meet"]
