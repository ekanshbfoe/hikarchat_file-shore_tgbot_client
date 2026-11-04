"""Saves a copy of the link list and settings to the Telegram backup channel."""

import gzip
import json
import logging
from datetime import UTC, datetime, timedelta

from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import BufferedInputFile

from bot import texts
from bot.app import App
from bot.services.notices import notify_owner_once

log = logging.getLogger(__name__)
LAST_BACKUP = "last_backup"
INTERVAL = timedelta(hours=24)
# Secrets and internal bookkeeping don't belong in a file sitting in a channel.
_NOT_BACKED_UP = {"shortener", LAST_BACKUP, "webhook_fingerprint"}


async def build_backup(app: App) -> bytes:
    settings = await app.settings.all()
    content = {
        "created_at": datetime.now(UTC).isoformat(),
        "settings": {k: v for k, v in settings.items() if k not in _NOT_BACKED_UP},
        "links": await app.links.export_all(),
    }
    return gzip.compress(json.dumps(content, ensure_ascii=False).encode())


async def run_backup(app: App) -> bool:
    """Returns whether the backup reached the channel."""
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    try:
        await app.bot.send_document(
            app.config.backup_channel_id,
            BufferedInputFile(await build_backup(app), filename=f"backup-{today}.json.gz"),
            caption=texts.BACKUP_CAPTION.format(date=today),
        )
    except (TelegramBadRequest, TelegramForbiddenError):
        log.warning("Backup could not be posted", exc_info=True)
        return False
    await app.settings.set(LAST_BACKUP, datetime.now(UTC).isoformat())
    return True


async def backup_if_due(app: App) -> None:
    last = await app.settings.get(LAST_BACKUP)
    if last and datetime.now(UTC) - datetime.fromisoformat(last) < INTERVAL:
        return
    if not await run_backup(app):
        await notify_owner_once(app, "backup_channel", texts.BACKUP_CHANNEL_NOTICE)


async def check_backup_channel(app: App) -> bool:
    """Tell the owner in plain words if the bot can't post where it needs to."""
    try:
        member = await app.bot.get_chat_member(app.config.backup_channel_id, app.bot.id)
        allowed = member.status in ("administrator", "creator")
    except (TelegramBadRequest, TelegramForbiddenError):
        allowed = False
    if not allowed:
        await notify_owner_once(app, "backup_channel", texts.BACKUP_CHANNEL_NOTICE)
    return allowed
