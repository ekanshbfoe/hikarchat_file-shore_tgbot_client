"""Telegram's command menu differs by role. This is only what people see: permissions
are always checked again on the server."""

import logging

from aiogram.types import (
    BotCommand,
    BotCommandScopeChat,
    BotCommandScopeDefault,
)

from bot import texts
from bot.app import App
from bot.db.roles import Role

log = logging.getLogger(__name__)
MENU_TTL = 24 * 3600.0

_USER = [BotCommand(command="start", description=texts.CMD_START)]
_STAFF = [
    *_USER,
    BotCommand(command="genlink", description=texts.CMD_GENLINK),
    BotCommand(command="universal_link", description=texts.CMD_UNIVERSAL),
    BotCommand(command="batch", description=texts.CMD_BATCH),
    BotCommand(command="special_link", description=texts.CMD_SPECIAL),
    BotCommand(command="shortener", description=texts.CMD_SHORTENER),
]
_STAFF_TAIL = [
    BotCommand(command="broadcast", description=texts.CMD_BROADCAST),
    BotCommand(command="ban", description=texts.CMD_BAN),
    BotCommand(command="unban", description=texts.CMD_UNBAN),
    BotCommand(command="cancel", description=texts.CMD_CANCEL),
]
_OWNER_ONLY = [BotCommand(command="settings", description=texts.CMD_SETTINGS)]


def commands_for(role: Role) -> list[BotCommand]:
    if role == Role.OWNER:
        return [*_STAFF, *_OWNER_ONLY, *_STAFF_TAIL]
    if role == Role.MODERATOR:
        return [*_STAFF, *_STAFF_TAIL]
    return list(_USER)


async def set_default_menu(app: App) -> None:
    await app.bot.set_my_commands(commands_for(Role.USER), scope=BotCommandScopeDefault())


async def sync_menu(app: App, user_id: int, role: Role) -> None:
    """Give a person the menu for their role, at most once a day. Never raises:
    a wrong menu must not stop anyone from using the bot."""
    key = f"menu:{user_id}"
    found, value, fresh = await app.store.cache.get(key)
    if found and fresh and value == role.value:
        return
    if role == Role.USER and not found:
        return  # Everyone already has the default menu.
    try:
        scope = BotCommandScopeChat(chat_id=user_id)
        if role == Role.USER:
            await app.bot.delete_my_commands(scope=scope)
        else:
            await app.bot.set_my_commands(commands_for(role), scope=scope)
        await app.store.cache.set(key, role.value, MENU_TTL)
    except Exception:
        log.info("Could not update the menu for %s", user_id, exc_info=True)


async def clear_menu(app: App, user_id: int) -> None:
    try:
        await app.bot.delete_my_commands(scope=BotCommandScopeChat(chat_id=user_id))
    except Exception:
        log.info("Could not clear the menu for %s", user_id, exc_info=True)
    await app.store.cache.delete(f"menu:{user_id}")
