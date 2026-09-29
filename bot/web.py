"""Маленький HTTP-сервер: сторінка події і .ics-файл для календаря.

Сторінка визначає систему за User-Agent: на Android — кнопка intent:// (форма нової
події в календарі телефону), на iPhone — перехід у Safari і .ics (див. нижче).

iPhone додає подію з .ics лише в справжньому Safari. Вбудований браузер Telegram
замість цього пропонує «підписатися на календар», тому кнопка в боті веде на сторінку
події з кнопкою «Відкрити в Safari» (x-safari-https://, iOS 17+) і «Додати в календар».
"""

import asyncio
import json
import logging
from html import escape

from aiogram import Bot
from aiohttp import web

from bot.cal_links import CAL_PATH, event_page_url, parse_token
from bot.config import Config
from bot.db import Database
from bot.events import Event, android_intent_url, build_ics, format_date, google_calendar_url, ics_filename
from bot.handlers.events_user import mark_opened

log = logging.getLogger(__name__)


def calendar_url(config: Config, event: Event) -> str:
    """Сторінка події (з неї — в Safari і в календар)."""
    return event_page_url(config, event.id)


_PAGE = """<!doctype html>
<html lang="uk">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
  :root {{ color-scheme: light dark; --bg:#f4f4f6; --card:#fff; --text:#1c1c1e; --muted:#6b6b70; --accent:#0a84ff; }}
  @media (prefers-color-scheme: dark) {{ :root {{ --bg:#000; --card:#1c1c1e; --text:#f2f2f7; --muted:#9a9aa0; }} }}
  body {{ margin:0; padding:24px 16px; background:var(--bg); color:var(--text);
         font:17px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
  main {{ max-width:440px; margin:0 auto; }}
  .card {{ background:var(--card); border-radius:16px; padding:20px; margin-bottom:16px; }}
  h1 {{ font-size:24px; margin:0 0 8px; }}
  .meta {{ color:var(--muted); margin:0; }}
  .step {{ color:var(--muted); font-size:15px; margin:0 0 10px; }}
  a.btn {{ display:block; text-align:center; text-decoration:none; font-weight:600; border-radius:12px;
          padding:15px; background:var(--accent); color:#fff; }}
  a.btn.secondary {{ background:transparent; color:var(--accent); border:1.5px solid var(--accent); }}
  .hint {{ color:var(--muted); font-size:14px; margin:12px 0 0; }}
</style>
</head>
<body>
<main>
  <div class="card">
    <h1>{title}</h1>
    <p class="meta">{meta}</p>
  </div>
{steps}
</main>
{script}
</body>
</html>
"""


_STEPS_TELEGRAM = """  <div class="card">
    <p class="step">Крок 1. Якщо ця сторінка відкрилась у Telegram — перейдіть у Safari:</p>
    <a class="btn secondary" href="{safari_url}">Відкрити в Safari</a>
    <p class="hint">Не спрацювало? Натисніть значок компаса або «⋯» внизу екрана → «Відкрити в Safari».</p>
  </div>
  <div class="card">
    <p class="step">Крок 2. У Safari натисніть:</p>
    <a class="btn" href="{ics_url}">📅 Додати в календар</a>
    <p class="hint">Якщо телефон пропонує «Підписатися на календар» — ви ще в Telegram, поверніться до кроку 1.</p>
  </div>
  <p class="hint">Користуєтесь Google Calendar? <a href="{google_url}">Додати через Google</a></p>"""

# Сторінку відкрито нашою кнопкою «Відкрити в Safari» — отже це справжній Safari
_STEPS_SAFARI = """  <div class="card">
    <p class="step">Відкриваю календар… Натисніть «Додати» у вікні, що з'явиться.</p>
    <a class="btn" href="{ics_url}">📅 Додати в календар</a>
    <p class="hint">Якщо вікно не з'явилось — натисніть кнопку вище.</p>
  </div>"""

# Android: системна форма «нова подія» в календарі телефону (Google, Samsung…), логін не потрібен
_STEPS_ANDROID = """  <div class="card">
    <a class="btn" href="{intent_url}">📅 Додати в календар</a>
    <p class="hint">Відкриється форма нової події в календарі телефону — натисніть «Зберегти».</p>
    <p class="hint">Не спрацювало? Натисніть «⋮» вгорі → «Відкрити в Chrome» і спробуйте ще раз.</p>
  </div>
  <p class="hint">Або <a href="{google_url}">додати через Google Calendar у браузері</a> (потрібен вхід у Google).</p>"""

_AUTO_OPEN = """<script>
  window.addEventListener("load", function () {{
    setTimeout(function () {{ window.location.href = {ics_url_js}; }}, 400);
  }});
</script>"""

def _page(config: Config, event: Event, in_safari: bool, android: bool = False) -> str:
    meta = format_date(event.day)
    if event.time:
        meta += f" · {event.time}"
    if event.place:
        meta += f"<br>{escape(event.place)}"
    page_url = calendar_url(config, event)
    ics_url = f"{page_url}.ics"
    if android:
        steps = _STEPS_ANDROID
    elif in_safari:
        steps = _STEPS_SAFARI
    else:
        steps = _STEPS_TELEGRAM
    return _PAGE.format(
        title=escape(event.title),
        meta=meta,
        steps=steps.format(
            safari_url=escape(f"x-safari-{page_url}?auto=1"),
            ics_url=escape(ics_url),
            google_url=escape(f"{page_url}/google"),
            intent_url=escape(android_intent_url(event, config.timezone)),
        ),
        script=_AUTO_OPEN.format(ics_url_js=json.dumps(ics_url)) if in_safari and not android else "",
    )


def create_app(bot: Bot, db: Database, config: Config) -> web.Application:
    def mark_from_link(request: web.Request, event: Event) -> None:
        """Сторінку відкрито кнопкою з постера — «✅ У календарі» (у фоні, щоб не гальмувати сторінку)."""
        parsed = parse_token(config, event.id, request.query.get("m", ""))
        if parsed:
            asyncio.create_task(mark_opened(bot, db, config, *parsed, event.id))

    async def health(_: web.Request) -> web.Response:
        return web.Response(text="ok")

    async def actual_event(request: web.Request) -> Event:
        try:
            event_id = int(request.match_info["event_id"])
        except ValueError:
            raise web.HTTPNotFound()
        event = await db.get_event(event_id)
        if not event or not event.day or event.day < config.today():
            raise web.HTTPNotFound(text="Подія неактуальна")
        return event

    async def event_page(request: web.Request) -> web.Response:
        event = await actual_event(request)
        mark_from_link(request, event)
        in_safari = request.query.get("auto") == "1"
        android = "android" in request.headers.get("User-Agent", "").lower()
        return web.Response(text=_page(config, event, in_safari, android), content_type="text/html", charset="utf-8")

    async def google(request: web.Request) -> web.Response:
        event = await actual_event(request)
        raise web.HTTPFound(google_calendar_url(event))

    async def event_ics(request: web.Request) -> web.Response:
        event = await actual_event(request)
        return web.Response(
            body=build_ics(event),
            content_type="text/calendar",
            charset="utf-8",
            headers={"Content-Disposition": f'inline; filename="{ics_filename(event)}"'},
        )

    app = web.Application()
    app.router.add_get(f"{CAL_PATH}/health", health)
    app.router.add_get(CAL_PATH + "/{event_id}.ics", event_ics)
    app.router.add_get(CAL_PATH + "/{event_id}/google", google)
    app.router.add_get(CAL_PATH + "/{event_id}", event_page)
    return app


async def start_web(bot: Bot, db: Database, config: Config) -> web.AppRunner:
    runner = web.AppRunner(create_app(bot, db, config), access_log=None)
    await runner.setup()
    await web.TCPSite(runner, config.web_host, config.web_port).start()
    log.info("Календарні посилання: %s%s/… (слухаю %s:%s)", config.public_url, CAL_PATH, config.web_host, config.web_port)
    return runner
