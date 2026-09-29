# Ключі таблиці settings
MEET_FORM_URL = "meet_form_url"
DONATIONS_URL = "donations_url"

# Розділ -> ключ налаштування з його посиланням
SECTION_URL_KEYS = {"meet": MEET_FORM_URL, "donations": DONATIONS_URL}

# Які елементи розділу редагуються через /settings
SECTION_FIELDS: dict[str, tuple[str, ...]] = {
    "meet": ("url",),
    "donations": ("photo", "text", "url"),
}
