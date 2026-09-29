"""Маленький HTTP-сервер: віддає .ics-файли подій за посиланням.

iPhone показує «Додати в календар» лише коли .ics відкривається в браузері,
а не як файл у Telegram, — тому кнопка веде сюди (через nginx з HTTPS).
"""

import logging

from aiohttp import web

from bot.config import Config
from bot.db import Database
from bot.events import Event, build_ics, ics_filename

log = logging.getLogger(__name__)

CAL_PATH = "/cal"


def calendar_url(config: Config, event: Event) -> str:
    return f"{config.public_url}{CAL_PATH}/{event.id}.ics"


def create_app(db: Database, config: Config) -> web.Application:
    async def health(_: web.Request) -> web.Response:
        return web.Response(text="ok")

    async def event_ics(request: web.Request) -> web.Response:
        try:
            event_id = int(request.match_info["event_id"])
        except ValueError:
            raise web.HTTPNotFound()
        event = await db.get_event(event_id)
        if not event or not event.day or event.day < config.today():
            raise web.HTTPNotFound(text="Подія неактуальна")
        return web.Response(
            body=build_ics(event),
            content_type="text/calendar",
            charset="utf-8",
            headers={"Content-Disposition": f'inline; filename="{ics_filename(event)}"'},
        )

    app = web.Application()
    app.router.add_get(f"{CAL_PATH}/health", health)
    app.router.add_get(CAL_PATH + "/{event_id}.ics", event_ics)
    return app


async def start_web(db: Database, config: Config) -> web.AppRunner:
    runner = web.AppRunner(create_app(db, config), access_log=None)
    await runner.setup()
    await web.TCPSite(runner, config.web_host, config.web_port).start()
    log.info("Календарні посилання: %s%s/… (слухаю %s:%s)", config.public_url, CAL_PATH, config.web_host, config.web_port)
    return runner
