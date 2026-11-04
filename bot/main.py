"""Starts the web server, then gets everything else ready in the background.

The port opens straight away so Render sees a healthy service even while a sleeping
database wakes up. Telegram gets "try again" from the webhook until startup finishes,
and it does retry, so nothing is lost.
"""

import asyncio
import hashlib
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.enums import ParseMode
from aiogram.webhook.aiohttp_server import SimpleRequestHandler
from aiohttp import web

from bot.app import App
from bot.config import Settings
from bot.db.engine import Database
from bot.db.local_cache import LocalCache
from bot.db.migrate import run_migrations
from bot.db.store import Store
from bot.dispatcher import build_dispatcher
from bot.menus import set_default_menu
from bot.retry import RetryMiddleware
from bot.services import backup, maintenance
from bot.web import add_health_routes

log = logging.getLogger(__name__)

ALLOWED_UPDATES = ["message", "callback_query", "chat_join_request"]
STARTUP_RETRY_SECONDS = 15.0
WEBHOOK_MAX_CONNECTIONS = 40
READY = web.AppKey("ready", asyncio.Event)


async def ensure_webhook(app: App) -> None:
    """Only touches Telegram's settings when something actually changed."""
    config = app.config
    fingerprint = hashlib.sha256(
        f"{config.webhook_url}|{config.secret_token}|{','.join(ALLOWED_UPDATES)}".encode()
    ).hexdigest()
    current = await app.bot.get_webhook_info()
    saved = await app.settings.get("webhook_fingerprint")
    if current.url == config.webhook_url and saved == fingerprint:
        return
    await app.bot.set_webhook(
        url=config.webhook_url,
        secret_token=config.secret_token,
        allowed_updates=ALLOWED_UPDATES,
        max_connections=WEBHOOK_MAX_CONNECTIONS,
    )
    await app.settings.set("webhook_fingerprint", fingerprint)
    log.info("Webhook registered")


async def prepare(app: App, migrate_url: str) -> None:
    await run_migrations(migrate_url)
    await app.bot.me()
    await app.roles.seed(app.config.moderator_usernames)
    await set_default_menu(app)
    await backup.check_backup_channel(app)
    await app.runner.resume_all()


async def _prepare_until_ready(
    app: App, migrate_url: str, ready: asyncio.Event, after_ready
) -> None:
    while True:
        try:
            await prepare(app, migrate_url)
            await after_ready()
            ready.set()
            log.info("Bot is ready")
            return
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Startup did not finish; trying again shortly")
            await asyncio.sleep(STARTUP_RETRY_SECONDS)


def build_web_app(app: App, dispatcher: Dispatcher) -> web.Application:
    config = app.config
    ready = asyncio.Event()
    web_app = web.Application()
    web_app[READY] = ready
    add_health_routes(web_app)

    webhook = SimpleRequestHandler(
        dispatcher=dispatcher,
        bot=app.bot,
        secret_token=config.secret_token,
        handle_in_background=True,
    )
    webhook.register(web_app, path=config.webhook_path)

    @web.middleware
    async def wait_until_ready(request: web.Request, handler):
        if request.path == config.webhook_path and not ready.is_set():
            # Telegram keeps the update and sends it again.
            return web.Response(status=503)
        return await handler(request)

    web_app.middlewares.append(wait_until_ready)
    return web_app


async def _lifecycle(web_app: web.Application, app: App, migrate_url: str):
    async def after_ready() -> None:
        await ensure_webhook(app)

    preparing = asyncio.create_task(
        _prepare_until_ready(app, migrate_url, web_app[READY], after_ready)
    )
    upkeep = asyncio.create_task(_run_upkeep_when_ready(web_app[READY], app))
    yield
    preparing.cancel()
    upkeep.cancel()
    await asyncio.gather(preparing, upkeep, return_exceptions=True)
    await app.runner.stop()
    await app.store.cache.close()
    await app.store.db.close()
    # The webhook is left in place: the next instance is already taking over.
    await app.bot.session.close()


async def _run_upkeep_when_ready(ready: asyncio.Event, app: App) -> None:
    await ready.wait()
    await maintenance.run_forever(app)


def build_bot(config: Settings) -> Bot:
    session = AiohttpSession()
    if config.telegram_api_url:
        session.api = TelegramAPIServer.from_base(config.telegram_api_url)
    bot = Bot(
        config.bot_token,
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    bot.session.middleware(RetryMiddleware())
    return bot


async def build(config: Settings) -> tuple[App, Dispatcher]:
    cache = LocalCache(config.local_cache_path)
    await cache.open()
    store = Store(Database(config.database_url), cache)
    app = App(config=config, bot=build_bot(config), store=store)
    return app, build_dispatcher(app)


async def run_webhook(config: Settings) -> None:
    app, dispatcher = await build(config)
    migrate_url = config.database_direct_url or config.database_url
    web_app = build_web_app(app, dispatcher)

    async def lifecycle(application: web.Application):
        async for _ in _lifecycle(application, app, migrate_url):
            yield

    web_app.cleanup_ctx.append(lifecycle)
    runner = web.AppRunner(web_app, handle_signals=True)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", config.port).start()
    log.info("Listening on port %s", config.port)
    try:
        await asyncio.Event().wait()
    finally:
        await runner.cleanup()


async def run_polling(config: Settings) -> None:
    """For trying the bot on a computer with no public address. Not for production."""
    app, dispatcher = await build(config)
    await prepare(app, config.database_direct_url or config.database_url)
    await app.bot.delete_webhook(drop_pending_updates=False)
    upkeep = asyncio.create_task(maintenance.run_forever(app))
    try:
        await dispatcher.start_polling(app.bot, allowed_updates=ALLOWED_UPDATES)
    finally:
        upkeep.cancel()
        await app.runner.stop()
        await app.store.cache.close()
        await app.store.db.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    # Request lines would write the webhook path, which is a secret, to the logs.
    logging.getLogger("aiohttp.access").setLevel(logging.WARNING)
    config = Settings()
    runner = run_polling if config.run_mode == "polling" else run_webhook
    try:
        asyncio.run(runner(config))
    except (KeyboardInterrupt, SystemExit, asyncio.CancelledError):
        log.info("Stopped")


if __name__ == "__main__":
    main()
