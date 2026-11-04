"""Runs before every handler: records the user, works out their role, stops banned users."""

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from bot import texts
from bot.app import App
from bot.db.engine import is_transient
from bot.db.roles import Role
from bot.menus import sync_menu
from bot.services.activity_log import actor

log = logging.getLogger(__name__)


class IdentityMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        app: App = data["app"]

        if isinstance(event, Message):
            if event.migrate_to_chat_id:
                await app.targets.migrate_chat(event.chat.id, event.migrate_to_chat_id)
                return None
            # The bot only works in private chat.
            if event.chat.type != "private":
                return None

        user = event.from_user
        if user is None or user.is_bot:
            return None

        try:
            if await app.users.touch(user.id, user.username, user.first_name):
                app.log.post(texts.LOG_NEW_USER.format(actor=actor(user)))
        except Exception as error:
            # Remembering a visitor isn't worth blocking them during a cloud hiccup.
            if not is_transient(error):
                raise
            log.warning("Could not record user %s", user.id)

        role = await app.roles.resolve(user.id, user.username)
        data["role"] = role

        if role == Role.USER and await app.users.is_banned(user.id):
            if isinstance(event, CallbackQuery):
                await event.answer(texts.BANNED, show_alert=True)
            else:
                await event.answer(texts.BANNED)
            return None

        await sync_menu(app, user.id, role)
        return await handler(event, data)
