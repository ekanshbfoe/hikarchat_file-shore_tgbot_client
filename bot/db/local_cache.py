"""Local SQLite read-through cache.

The disk is wiped whenever Render restarts the service, so nothing here is ever the
only copy of anything. Any failure is swallowed: the bot simply carries on with
the cloud database while the cache is rebuilt.
"""

import json
import logging
import os
import time
from typing import Any

import aiosqlite

log = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS cache (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    expires_at REAL NOT NULL
)
"""


class LocalCache:
    def __init__(self, path: str):
        self.path = path
        self._conn: aiosqlite.Connection | None = None

    async def open(self) -> None:
        try:
            await self._open()
        except Exception:
            log.warning("Local cache unavailable, recreating it", exc_info=True)
            await self._recreate()

    async def _open(self) -> None:
        self._conn = await aiosqlite.connect(self.path)
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.execute("PRAGMA synchronous=OFF")
        await self._conn.execute(_SCHEMA)
        await self._conn.commit()

    async def _recreate(self) -> None:
        await self.close()
        for suffix in ("", "-wal", "-shm"):
            try:
                os.remove(self.path + suffix)
            except OSError:
                pass
        try:
            await self._open()
        except Exception:
            log.warning("Local cache could not be recreated", exc_info=True)
            await self.close()

    async def close(self) -> None:
        if self._conn is not None:
            conn, self._conn = self._conn, None
            try:
                await conn.close()
            except Exception:
                log.debug("Ignoring failure while closing the cache", exc_info=True)

    async def get(self, key: str) -> tuple[bool, Any, bool]:
        """Returns (found, value, is_fresh). Expired entries are still returned so
        they can stand in during a cloud outage."""
        if self._conn is None:
            return False, None, False
        try:
            cursor = await self._conn.execute(
                "SELECT value, expires_at FROM cache WHERE key = ?", (key,)
            )
            row = await cursor.fetchone()
            await cursor.close()
            if row is None:
                return False, None, False
            return True, json.loads(row[0]), row[1] > time.time()
        except Exception:
            log.warning("Local cache read failed, rebuilding it", exc_info=True)
            await self._recreate()
            return False, None, False

    async def set(self, key: str, value: Any, ttl: float) -> None:
        if self._conn is None:
            return
        try:
            await self._conn.execute(
                "INSERT INTO cache (key, value, expires_at) VALUES (?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value, "
                "expires_at = excluded.expires_at",
                (key, json.dumps(value), time.time() + ttl),
            )
            await self._conn.commit()
        except Exception:
            log.warning("Local cache write failed, rebuilding it", exc_info=True)
            await self._recreate()

    async def delete(self, *keys: str) -> None:
        if self._conn is None or not keys:
            return
        try:
            await self._conn.executemany("DELETE FROM cache WHERE key = ?", [(k,) for k in keys])
            await self._conn.commit()
        except Exception:
            log.warning("Local cache delete failed, rebuilding it", exc_info=True)
            await self._recreate()

    async def delete_prefix(self, prefix: str) -> None:
        if self._conn is None:
            return
        try:
            escaped = prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            await self._conn.execute(
                "DELETE FROM cache WHERE key LIKE ? ESCAPE '\\'", (f"{escaped}%",)
            )
            await self._conn.commit()
        except Exception:
            log.warning("Local cache delete failed, rebuilding it", exc_info=True)
            await self._recreate()
