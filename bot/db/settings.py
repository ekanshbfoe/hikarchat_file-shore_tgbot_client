"""Key-value settings the owner changes from inside the bot."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from bot.db.models import settings
from bot.db.store import SHORT_TTL, Store


class SettingsRepo:
    def __init__(self, store: Store):
        self.store = store

    async def get(self, key: str, default: Any = None) -> Any:
        async def loader(conn):
            row = (
                await conn.execute(select(settings.c.value).where(settings.c.key == key))
            ).first()
            return row.value if row else None

        value = await self.store.read_through(f"setting:{key}", SHORT_TTL, loader)
        return default if value is None else value

    async def get_many(self, *keys: str) -> dict[str, Any]:
        """Several settings for one round trip. A missing one comes back as None, the
        same as get() before its default is applied."""
        values: dict[str, Any] = {}
        wanted: list[str] = []
        for key in keys:
            found, value, fresh = await self.store.cache.get(f"setting:{key}")
            if found and fresh:
                values[key] = value
            else:
                wanted.append(key)
        if wanted:

            async def loader(conn):
                rows = await conn.execute(
                    select(settings.c.key, settings.c.value).where(settings.c.key.in_(wanted))
                )
                return {row.key: row.value for row in rows}

            loaded = await self.store.db.read(loader)
            for key in wanted:
                value = loaded.get(key)
                values[key] = value
                if value is None:
                    await self.store.cache.delete(f"setting:{key}")
                else:
                    await self.store.cache.set(f"setting:{key}", value, SHORT_TTL)
        return values

    async def set(self, key: str, value: Any) -> None:
        statement = insert(settings).values(key=key, value=value)
        async with self.store.db.write() as conn:
            await conn.execute(
                statement.on_conflict_do_update(
                    index_elements=[settings.c.key], set_={"value": value}
                )
            )
        await self.store.cache.set(f"setting:{key}", value, SHORT_TTL)

    async def all(self) -> dict[str, Any]:
        async def loader(conn):
            rows = await conn.execute(select(settings.c.key, settings.c.value))
            return {row.key: row.value for row in rows}

        return await self.store.db.read(loader)
