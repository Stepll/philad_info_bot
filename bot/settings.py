# Ключі таблиці settings
MEET_FORM_URL = "meet_form_url"
DONATIONS_URL = "donations_url"
HOMEGROUPS_URL = "homegroups_url"
# file_id останньої згенерованої картинки розкладу (скидається після кожної зміни)
SCHEDULE_FILE_ID = "schedule_file_id"

# Розділ -> ключ налаштування з його посиланням
SECTION_URL_KEYS = {"meet": MEET_FORM_URL, "donations": DONATIONS_URL, "homegroups": HOMEGROUPS_URL}

# Розділи «фото + текст + кнопка-посилання»: текст кнопки для користувачів
SECTION_URL_BUTTONS = {
    "donations": "💛 Пожертвувати онлайн",
    "homegroups": "🏠 Долучитися до групи",
}

# Які елементи розділу редагуються через /settings
SECTION_FIELDS: dict[str, tuple[str, ...]] = {
    "welcome": ("photo", "text"),
    "meet": ("url",),
    "donations": ("photo", "text", "url"),
    "homegroups": ("photo", "text", "url"),
}
