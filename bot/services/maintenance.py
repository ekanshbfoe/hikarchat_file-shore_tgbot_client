"""Quiet upkeep that runs in the background: daily backup and invite link checks."""

import asyncio
import logging

from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

from bot import texts
from bot.app import App
from bot.db.targets import TELEGRAM
from bot.services import backup
from bot.services.notices import notify_owner_once

log = logging.getLogger(__name__)
CHECK_EVERY_SECONDS = 3600.0
INVITE_LINK_NAME = "Force subscribe"


async def refresh_invite_links(app: App) -> None:
    """A private channel's link may have been revoked. Editing a revoked link fails,
    which tells us to make a new one, so people always get a working link."""
    for target in await app.targets.list_active():
        url = target["url"] or ""
        if target["platform"] != TELEGRAM or "/+" not in url:
            continue  # Public chats have a permanent address.
        try:
            await app.bot.edit_chat_invite_link(
                target["chat_id"], invite_link=url, name=INVITE_LINK_NAME
            )
            continue
        except TelegramForbiddenError:
            await _cannot_reach(app, target)
            continue
        except TelegramBadRequest:
            log.info("Invite link for target %s needs replacing", target["id"])
        try:
            link = await app.bot.create_chat_invite_link(target["chat_id"], name=INVITE_LINK_NAME)
            await app.targets.set_url(target["id"], link.invite_link)
        except (TelegramBadRequest, TelegramForbiddenError):
            await _cannot_reach(app, target)


async def _cannot_reach(app: App, target: dict) -> None:
    await notify_owner_once(
        app,
        f"target:{target['id']}",
        texts.FS_CHAT_NOTICE.format(name=texts.esc(target["display_name"])),
    )


async def run_once(app: App) -> None:
    last = await app.settings.get(backup.LAST_BACKUP)
    await backup.backup_if_due(app)
    if last != await app.settings.get(backup.LAST_BACKUP):
        await refresh_invite_links(app)  # Once a day, alongside the backup.


async def run_forever(app: App) -> None:
    while True:
        try:
            await run_once(app)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Daily upkeep failed; will try again later")
        await asyncio.sleep(CHECK_EVERY_SECONDS)
