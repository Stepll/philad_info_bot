from dataclasses import dataclass
from datetime import date
from pathlib import Path

import aiosqlite

from bot.events import Event
from bot.schedule import SEED, ScheduleItem
from bot.sections import SECTIONS

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sections (
    key        TEXT PRIMARY KEY,
    text       TEXT,
    photo_id   TEXT,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_by INTEGER
);
CREATE TABLE IF NOT EXISTS settings (
    key        TEXT PRIMARY KEY,
    value      TEXT,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_by INTEGER
);
CREATE TABLE IF NOT EXISTS schedule_items (
    id    INTEGER PRIMARY KEY AUTOINCREMENT,
    day   INTEGER NOT NULL,
    time  TEXT NOT NULL,
    title TEXT NOT NULL,
    color TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    poster_id  TEXT NOT NULL,
    text       TEXT NOT NULL DEFAULT '',
    date       TEXT,
    time       TEXT,
    place      TEXT,
    url        TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS event_calendar (
    user_id    INTEGER NOT NULL,
    event_id   INTEGER NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, event_id)
);
"""

_EVENT_COLUMNS = {"poster_id", "text", "date", "time", "place", "url"}
_EVENT_SELECT = "SELECT id, poster_id, text, date, time, place, url FROM events"

_SCHEDULE_SEEDED = "schedule_seeded"
_SCHEDULE_COLUMNS = {"day", "time", "title", "color"}


@dataclass
class SectionContent:
    text: str
    photo_id: str | None


class Database:
    def __init__(self, path: str):
        self.path = path

    async def init(self) -> None:
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.path) as db:
            await db.executescript(_SCHEMA)
            await db.commit()
        if not await self.get_setting(_SCHEDULE_SEEDED):
            for day, time, title, color in SEED:
                await self.add_schedule_item(day, time, title, color)
            await self.set_setting(_SCHEDULE_SEEDED, "1", 0)

    async def get_section(self, key: str) -> SectionContent:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute("SELECT text, photo_id FROM sections WHERE key = ?", (key,))
            row = await cur.fetchone()
        # NULL — стандартний текст; порожній рядок — текст видалено адміном
        text = row[0] if row and row[0] is not None else SECTIONS[key].default_text
        return SectionContent(text=text, photo_id=row[1] if row else None)

    async def _upsert(self, key: str, column: str, value: str | None, user_id: int) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                f"""
                INSERT INTO sections (key, {column}, updated_by) VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    {column} = excluded.{column},
                    updated_by = excluded.updated_by,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (key, value, user_id),
            )
            await db.commit()

    async def set_text(self, key: str, text: str | None, user_id: int) -> None:
        await self._upsert(key, "text", text, user_id)

    async def set_photo(self, key: str, photo_id: str | None, user_id: int) -> None:
        await self._upsert(key, "photo_id", photo_id, user_id)

    async def get_setting(self, key: str) -> str | None:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute("SELECT value FROM settings WHERE key = ?", (key,))
            row = await cur.fetchone()
        return row[0] if row else None

    async def set_setting(self, key: str, value: str | None, user_id: int) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """
                INSERT INTO settings (key, value, updated_by) VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_by = excluded.updated_by,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (key, value, user_id),
            )
            await db.commit()

    # --- Розклад ---

    async def list_schedule(self) -> list[ScheduleItem]:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute("SELECT id, day, time, title, color FROM schedule_items")
            rows = await cur.fetchall()
        items = [ScheduleItem(*row) for row in rows]
        return sorted(items, key=lambda i: (i.day, i.minutes, i.id))

    async def get_schedule_item(self, item_id: int) -> ScheduleItem | None:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(
                "SELECT id, day, time, title, color FROM schedule_items WHERE id = ?", (item_id,)
            )
            row = await cur.fetchone()
        return ScheduleItem(*row) if row else None

    async def add_schedule_item(self, day: int, time: str, title: str, color: str) -> int:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(
                "INSERT INTO schedule_items (day, time, title, color) VALUES (?, ?, ?, ?)",
                (day, time, title, color),
            )
            await db.commit()
            return cur.lastrowid

    async def update_schedule_item(self, item_id: int, column: str, value: str | int) -> None:
        if column not in _SCHEDULE_COLUMNS:
            raise ValueError(column)
        async with aiosqlite.connect(self.path) as db:
            await db.execute(f"UPDATE schedule_items SET {column} = ? WHERE id = ?", (value, item_id))
            await db.commit()

    async def delete_schedule_item(self, item_id: int) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute("DELETE FROM schedule_items WHERE id = ?", (item_id,))
            await db.commit()

    # --- Події ---

    async def list_events(self) -> list[Event]:
        """Усі події: чернетки (без дати) першими, далі за датою і часом."""
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(_EVENT_SELECT)
            rows = await cur.fetchall()
        events = [Event(*row) for row in rows]
        return sorted(events, key=lambda e: (e.date is not None, e.date or "", _minutes(e.time), e.id))

    async def upcoming_events(self, today: date) -> list[Event]:
        return [e for e in await self.list_events() if e.day and e.day >= today]

    async def get_event(self, event_id: int) -> Event | None:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(f"{_EVENT_SELECT} WHERE id = ?", (event_id,))
            row = await cur.fetchone()
        return Event(*row) if row else None

    async def add_event(self, poster_id: str) -> int:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute("INSERT INTO events (poster_id) VALUES (?)", (poster_id,))
            await db.commit()
            return cur.lastrowid

    async def update_event(self, event_id: int, column: str, value: str | None) -> None:
        if column not in _EVENT_COLUMNS:
            raise ValueError(column)
        async with aiosqlite.connect(self.path) as db:
            await db.execute(f"UPDATE events SET {column} = ? WHERE id = ?", (value, event_id))
            await db.commit()

    async def delete_event(self, event_id: int) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute("DELETE FROM events WHERE id = ?", (event_id,))
            await db.execute("DELETE FROM event_calendar WHERE event_id = ?", (event_id,))
            await db.commit()

    async def purge_events_before(self, cutoff: date) -> None:
        """Видаляє події, що минули до cutoff (разом з відмітками «в календарі»)."""
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "DELETE FROM event_calendar WHERE event_id IN (SELECT id FROM events WHERE date < ?)",
                (cutoff.isoformat(),),
            )
            await db.execute("DELETE FROM events WHERE date < ?", (cutoff.isoformat(),))
            await db.commit()

    async def mark_in_calendar(self, user_id: int, event_id: int) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "INSERT OR IGNORE INTO event_calendar (user_id, event_id) VALUES (?, ?)", (user_id, event_id)
            )
            await db.commit()

    async def is_in_calendar(self, user_id: int, event_id: int) -> bool:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(
                "SELECT 1 FROM event_calendar WHERE user_id = ? AND event_id = ?", (user_id, event_id)
            )
            return await cur.fetchone() is not None

    async def calendar_count(self, event_id: int) -> int:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute("SELECT COUNT(*) FROM event_calendar WHERE event_id = ?", (event_id,))
            return (await cur.fetchone())[0]


def _minutes(time: str | None) -> int:
    if not time:
        return -1
    h, m = time.split(":")
    return int(h) * 60 + int(m)
