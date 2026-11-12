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
# The owner menu is short but important: re-assert it hourly so a wiped menu heals
# by itself instead of staying wrong until the next restart.
OWNER_MENU_TTL = 3600.0

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


async def _apply(app: App, user_id: int, role: Role) -> None:
    scope = BotCommandScopeChat(chat_id=user_id)
    if role == Role.USER:
        await app.bot.delete_my_commands(scope=scope)
    else:
        await app.bot.set_my_commands(commands_for(role), scope=scope)
    ttl = OWNER_MENU_TTL if role == Role.OWNER else MENU_TTL
    await app.store.cache.set(f"menu:{user_id}", role.value, ttl)


async def set_default_menu(app: App) -> None:
    """Called once at startup, before anybody has to go looking for a command."""
    await app.bot.set_my_commands(commands_for(Role.USER), scope=BotCommandScopeDefault())
    for user_id in sorted(app.config.owner_ids):
        try:
            await _apply(app, user_id, Role.OWNER)
        except Exception:
            # Telegram only knows chats that have already talked to the bot; the rest
            # get their menu from sync_menu on their first message.
            log.info("Owner %s has not opened the bot yet", user_id)


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
        await _apply(app, user_id, role)
    except Exception:
        log.info("Could not update the menu for %s", user_id, exc_info=True)


async def clear_menu(app: App, user_id: int) -> None:
    if app.roles.is_owner(user_id):
        # Removing a moderator row must not take the owner's own menu away.
        try:
            await _apply(app, user_id, Role.OWNER)
        except Exception:
            log.info("Could not restore the menu for %s", user_id, exc_info=True)
        return
    try:
        await app.bot.delete_my_commands(scope=BotCommandScopeChat(chat_id=user_id))
    except Exception:
        log.info("Could not clear the menu for %s", user_id, exc_info=True)
    await app.store.cache.delete(f"menu:{user_id}")
