"""Маленький HTTP-сервер: сторінка події і .ics-файл для календаря.

iPhone додає подію з .ics лише в справжньому Safari. Вбудований браузер Telegram
замість цього пропонує «підписатися на календар», тому кнопка в боті веде на сторінку
події з кнопкою «Відкрити в Safari» (x-safari-https://, iOS 17+) і «Додати в календар».
"""

import json
import logging
from html import escape

from aiohttp import web

from bot.config import Config
from bot.db import Database
from bot.events import Event, build_ics, format_date, ics_filename

log = logging.getLogger(__name__)

CAL_PATH = "/cal"


def calendar_url(config: Config, event: Event) -> str:
    """Сторінка події (з неї — в Safari і в календар)."""
    return f"{config.public_url}{CAL_PATH}/{event.id}"


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
  </div>"""

# Сторінку відкрито нашою кнопкою «Відкрити в Safari» — отже це справжній Safari
_STEPS_SAFARI = """  <div class="card">
    <p class="step">Відкриваю календар… Натисніть «Додати» у вікні, що з'явиться.</p>
    <a class="btn" href="{ics_url}">📅 Додати в календар</a>
    <p class="hint">Якщо вікно не з'явилось — натисніть кнопку вище.</p>
  </div>"""

_AUTO_OPEN = """<script>
  window.addEventListener("load", function () {{
    setTimeout(function () {{ window.location.href = {ics_url_js}; }}, 400);
  }});
</script>"""

def _page(config: Config, event: Event, in_safari: bool) -> str:
    meta = format_date(event.day)
    if event.time:
        meta += f" · {event.time}"
    if event.place:
        meta += f"<br>{escape(event.place)}"
    page_url = calendar_url(config, event)
    ics_url = f"{page_url}.ics"
    steps = _STEPS_SAFARI if in_safari else _STEPS_TELEGRAM
    return _PAGE.format(
        title=escape(event.title),
        meta=meta,
        steps=steps.format(safari_url=escape(f"x-safari-{page_url}?auto=1"), ics_url=escape(ics_url)),
        script=_AUTO_OPEN.format(ics_url_js=json.dumps(ics_url)) if in_safari else "",
    )


def create_app(db: Database, config: Config) -> web.Application:
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
        in_safari = request.query.get("auto") == "1"
        return web.Response(text=_page(config, event, in_safari), content_type="text/html", charset="utf-8")

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
    app.router.add_get(CAL_PATH + "/{event_id}", event_page)
    return app


async def start_web(db: Database, config: Config) -> web.AppRunner:
    runner = web.AppRunner(create_app(db, config), access_log=None)
    await runner.setup()
    await web.TCPSite(runner, config.web_host, config.web_port).start()
    log.info("Календарні посилання: %s%s/… (слухаю %s:%s)", config.public_url, CAL_PATH, config.web_host, config.web_port)
    return runner
