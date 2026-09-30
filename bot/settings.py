# Ключі таблиці settings
MEET_FORM_URL = "meet_form_url"
DONATIONS_URL = "donations_url"
HOMEGROUPS_URL = "homegroups_url"
SOCIALS_URL = "socials_url"
NEEDS_URL = "needs_url"
# file_id останньої згенерованої картинки розкладу (скидається після кожної зміни)
SCHEDULE_FILE_ID = "schedule_file_id"

# Розділ -> ключ налаштування з його посиланням
SECTION_URL_KEYS = {"meet": MEET_FORM_URL, "donations": DONATIONS_URL, "homegroups": HOMEGROUPS_URL, "socials": SOCIALS_URL, "needs": NEEDS_URL}

# Розділи «фото + текст + кнопка-посилання»: текст кнопки для користувачів
SECTION_URL_BUTTONS = {
    "donations": "💛 Пожертвувати онлайн",
    "homegroups": "🏠 Долучитися до групи",
    "socials": "📲 Перейти",
}

# Які елементи розділу редагуються через /settings
SECTION_FIELDS: dict[str, tuple[str, ...]] = {
    "welcome": ("photo", "text"),
    "meet": ("url",),
    "needs": ("url",),
    "donations": ("photo", "text", "url"),
    "homegroups": ("photo", "text", "url"),
    "socials": ("photo", "text", "url"),
}

# Розділи «лише кнопка-посилання»: (текст повідомлення, текст кнопки, текст, поки посилання немає)
LINK_SECTIONS = {
    "meet": ("Давайте знайомитись! 👇", "📝 Заповнити анкету", "Анкета незабаром з'явиться 🙏"),
    "needs": ("Поділіться своєю потребою 👇", "🙏 Перейти", "Незабаром тут з'явиться посилання 🙏"),
}
