"""Події: модель, форматування підпису, файл календаря (.ics) і посилання на Google Calendar."""

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from html import escape, unescape
from urllib.parse import quote, urlencode
from zoneinfo import ZoneInfo

# Підпис під фото — до 1024 символів; решту займає рядок з датою/часом/місцем
EVENT_TEXT_LIMIT = 850
PLACE_MAX_LEN = 100
# Скільки днів минула подія ще лежить в адмінці, перш ніж бот її видалить
KEEP_PAST_DAYS = 30
# Тривалість для календаря, якщо задано час (календарю потрібен кінець)
CALENDAR_DURATION = timedelta(hours=2)


@dataclass
class Event:
    id: int
    poster_id: str
    text: str  # HTML
    date: str | None  # ISO "YYYY-MM-DD"; None — чернетка (людям не показується)
    time: str | None  # "H:MM"
    place: str | None
    url: str | None

    @property
    def day(self) -> date | None:
        return date.fromisoformat(self.date) if self.date else None

    @property
    def title(self) -> str:
        """Перший рядок тексту — назва події (для списку в адмінці й календаря)."""
        first = html_to_plain(self.text).strip().split("\n", 1)[0].strip()
        return first or "Подія"


def html_to_plain(html: str) -> str:
    return unescape(re.sub(r"<[^>]+>", "", html or ""))


def parse_date(value: str) -> date | None:
    """'12.10.2026', '12/10/2026', '12-10-2026' -> date; рік обов'язковий."""
    match = re.fullmatch(r"\s*(\d{1,2})[./-](\d{1,2})[./-](\d{4})\s*", value)
    if not match:
        return None
    try:
        return date(int(match[3]), int(match[2]), int(match[1]))
    except ValueError:
        return None


def format_date(d: date) -> str:
    return d.strftime("%d.%m.%Y")


def caption(event: Event) -> str:
    """Підпис під постером: дата · час, місце, потім текст."""
    head = []
    if event.day:
        when = f"📅 {format_date(event.day)}"
        if event.time:
            when += f" · 🕐 {event.time}"
        head.append(when)
    if event.place:
        head.append(f"📍 {escape(event.place)}")
    parts = ["\n".join(head)] if head else []
    if event.text:
        parts.append(event.text)
    return "\n\n".join(parts)


# --- Календар ----------------------------------------------------------------


def _bounds(event: Event) -> tuple[str, str, bool]:
    """(початок, кінець, чи весь день) у форматі календаря. Час «плаваючий» — за часом телефону."""
    if event.time:
        h, m = map(int, event.time.split(":"))
        start = datetime.combine(event.day, datetime.min.time()).replace(hour=h, minute=m)
        end = start + CALENDAR_DURATION
        fmt = "%Y%m%dT%H%M%S"
        return start.strftime(fmt), end.strftime(fmt), False
    return event.day.strftime("%Y%m%d"), (event.day + timedelta(days=1)).strftime("%Y%m%d"), True


def _ics_escape(value: str) -> str:
    return (
        value.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\r\n", "\n").replace("\n", "\\n")
    )


def _ics_fold(line: str) -> str:
    """Рядки .ics — не довші за 75 байт; продовження починається з пробілу."""
    out, current = [], b""
    for ch in line:
        encoded = ch.encode()
        if len(current) + len(encoded) > (75 if not out else 74):
            out.append(current.decode())
            current = b""
        current += encoded
    out.append(current.decode())
    return "\r\n ".join(out)


def build_ics(event: Event) -> bytes:
    start, end, all_day = _bounds(event)
    date_param = ";VALUE=DATE" if all_day else ""
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//philad_info_bot//UA",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        f"UID:event-{event.id}@philad-info-bot",
        f"DTSTAMP:{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
        f"DTSTART{date_param}:{start}",
        f"DTEND{date_param}:{end}",
        f"SUMMARY:{_ics_escape(event.title)}",
    ]
    if event.place:
        lines.append(f"LOCATION:{_ics_escape(event.place)}")
    description = html_to_plain(event.text).strip()
    if event.url:
        description = f"{description}\n\n{event.url}".strip()
    if description:
        lines.append(f"DESCRIPTION:{_ics_escape(description)}")
    if event.url:
        lines.append(f"URL:{event.url}")
    lines += ["END:VEVENT", "END:VCALENDAR"]
    return ("\r\n".join(_ics_fold(line) for line in lines) + "\r\n").encode()


def ics_filename(event: Event) -> str:
    return f"event-{event.date}.ics"


def google_calendar_url(event: Event) -> str:
    start, end, _ = _bounds(event)
    details = html_to_plain(event.text).strip()
    if len(details) > 500:
        details = details[:500] + "…"
    params = {"action": "TEMPLATE", "text": event.title, "dates": f"{start}/{end}", "details": details}
    if event.place:
        params["location"] = event.place
    return "https://calendar.google.com/calendar/render?" + urlencode(params)


def android_intent_url(event: Event, timezone_name: str) -> str:
    """intent:// для Chrome на Android: відкриває форму нової події в календарі телефону.

    Android приймає час у мілісекундах від епохи, тому «плаваючий» час події прив'язуємо
    до часового поясу церкви. Для події на весь день — опівніч UTC, як вимагає Android.
    """
    if event.time:
        h, m = map(int, event.time.split(":"))
        start = datetime.combine(event.day, datetime.min.time()).replace(hour=h, minute=m, tzinfo=ZoneInfo(timezone_name))
        end = start + CALENDAR_DURATION
        all_day = False
    else:
        start = datetime.combine(event.day, datetime.min.time(), tzinfo=timezone.utc)
        end = start + timedelta(days=1)
        all_day = True

    description = html_to_plain(event.text).strip()
    if event.url:
        description = f"{description}\n\n{event.url}".strip()
    if len(description) > 500:
        description = description[:500] + "…"

    extras = [
        "action=android.intent.action.INSERT",
        "type=vnd.android.cursor.item/event",
        f"S.title={quote(event.title, safe='')}",
        f"l.beginTime={int(start.timestamp() * 1000)}",
        f"l.endTime={int(end.timestamp() * 1000)}",
    ]
    if all_day:
        extras.append("B.allDay=true")
    if event.place:
        extras.append(f"S.eventLocation={quote(event.place, safe='')}")
    if description:
        extras.append(f"S.description={quote(description, safe='')}")
    return "intent:#Intent;" + ";".join(extras) + ";end"
