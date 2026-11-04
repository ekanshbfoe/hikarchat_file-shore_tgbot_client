"""Local-first reads with the cloud database as the source of truth."""

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from bot.db.engine import Database, is_transient
from bot.db.local_cache import LocalCache

log = logging.getLogger(__name__)

# Things that change and that a second instance could change during a deploy.
SHORT_TTL = 60.0
# Things that never change once written.
LONG_TTL = 7 * 24 * 3600.0


class Store:
    def __init__(self, db: Database, cache: LocalCache):
        self.db = db
        self.cache = cache

    async def read_through(
        self,
        key: str,
        ttl: float | Callable[[Any], float],
        loader: Callable[..., Awaitable[Any]],
    ) -> Any:
        """Local first, then cloud. None ("not found") is never cached, so a brand new
        record is visible at once. If the cloud is down an expired copy stands in."""
        found, value, fresh = await self.cache.get(key)
        if found and fresh:
            return value
        try:
            loaded = await self.db.read(loader)
        except Exception as error:
            if found and is_transient(error):
                log.warning("Cloud database unavailable, serving %s from local copy", key)
                return value
            raise
        if loaded is None:
            await self.cache.delete(key)
        else:
            await self.cache.set(key, loaded, ttl(loaded) if callable(ttl) else ttl)
        return loaded
