"""Assembles the dispatcher. Order matters: commands come before conversations, so a
command always works, and the fallback comes last."""

from aiogram import Dispatcher
from aiogram.fsm.storage.base import BaseEventIsolation
from aiogram.fsm.storage.memory import SimpleEventIsolation

from bot.app import App
from bot.db.fsm_storage import PostgresStorage
from bot.errors import on_error
from bot.handlers import (
    batch,
    broadcast,
    fallback,
    links,
    moderation,
    settings,
    shortener,
    special,
    start,
)
from bot.middlewares import IdentityMiddleware
from bot.services import batch as batch_service
from bot.services import broadcast as broadcast_service
from bot.services.runner import JobRunner


def _build_runner(app: App) -> JobRunner:
    runner = JobRunner(app)
    runner.register(batch_service.KIND, batch_service.run)
    runner.register(broadcast_service.KIND, broadcast_service.run)
    return runner


def build_dispatcher(app: App, events_isolation: BaseEventIsolation | None = None) -> Dispatcher:
    # Isolation handles one person's updates in order, so albums and several
    # screenshots sent together can't overwrite each other.
    dispatcher = Dispatcher(
        storage=PostgresStorage(app.store),
        events_isolation=events_isolation or SimpleEventIsolation(),
    )
    dispatcher["app"] = app
    app.runner = _build_runner(app)

    identity = IdentityMiddleware()
    dispatcher.message.outer_middleware(identity)
    dispatcher.callback_query.outer_middleware(identity)
    dispatcher.errors.register(on_error)

    dispatcher.include_router(start.router)
    dispatcher.include_router(moderation.router)
    dispatcher.include_router(batch.router)
    dispatcher.include_router(special.router)
    dispatcher.include_router(links.router)
    dispatcher.include_router(shortener.router)
    dispatcher.include_router(settings.router)
    dispatcher.include_router(broadcast.router)
    dispatcher.include_router(fallback.router)
    return dispatcher
