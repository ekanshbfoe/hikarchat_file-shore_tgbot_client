"""Tells the owner about things only they can fix, without nagging."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bot.app import App

log = logging.getLogger(__name__)
QUIET_SECONDS = 24 * 3600.0


async def notify_owner_once(app: App, key: str, text: str) -> None:
    cache_key = f"notice:{key}"
    found, _, fresh = await app.store.cache.get(cache_key)
    if found and fresh:
        return
    try:
        await app.bot.send_message(app.config.owner_id, text)
        await app.store.cache.set(cache_key, True, QUIET_SECONDS)
    except Exception:
        log.info("Could not reach the owner", exc_info=True)
