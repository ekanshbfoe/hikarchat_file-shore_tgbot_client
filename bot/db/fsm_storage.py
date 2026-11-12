"""Conversation state that survives restarts: saved to Postgres, read locally first."""

from typing import Any

from aiogram.fsm.state import State
from aiogram.fsm.storage.base import BaseStorage, StateType, StorageKey
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert

from bot.db.models import fsm_state
from bot.db.store import LONG_TTL, Store


def _key(key: StorageKey) -> str:
    return f"{key.bot_id}:{key.chat_id}:{key.user_id}"


# "No conversation" is the usual answer for a message, and aiogram asks for the state of
# every single update. Remembering the empty answer briefly keeps that off the cloud.
ABSENT_TTL = 60.0


class PostgresStorage(BaseStorage):
    def __init__(self, store: Store):
        self.store = store

    async def _load(self, row_key: str) -> dict[str, Any]:
        async def loader(conn):
            row = (
                await conn.execute(
                    select(fsm_state.c.state, fsm_state.c.data).where(fsm_state.c.key == row_key)
                )
            ).first()
            return {"state": row.state, "data": row.data} if row else None

        loaded = await self.store.read_through(
            f"fsm:{row_key}", LONG_TTL, loader, none_ttl=ABSENT_TTL
        )
        return loaded or {"state": None, "data": {}}

    async def _save(self, row_key: str, state: str | None, data: dict[str, Any]) -> None:
        key = f"fsm:{row_key}"
        if state is None and not data:
            found, value, _ = await self.store.cache.get(key)
            if found and value is None:
                return  # There was never a row, so there is nothing to delete.
            async with self.store.db.write() as conn:
                await conn.execute(delete(fsm_state).where(fsm_state.c.key == row_key))
            await self.store.cache.set(key, None, ABSENT_TTL)
            return
        async with self.store.db.write() as conn:
            statement = insert(fsm_state).values(key=row_key, state=state, data=data)
            await conn.execute(
                statement.on_conflict_do_update(
                    index_elements=[fsm_state.c.key],
                    set_={"state": state, "data": data},
                )
            )
        await self.store.cache.set(key, {"state": state, "data": data}, LONG_TTL)

    async def set_state(self, key: StorageKey, state: StateType = None) -> None:
        row_key = _key(key)
        current = await self._load(row_key)
        value = state.state if isinstance(state, State) else state
        await self._save(row_key, value, current["data"])

    async def get_state(self, key: StorageKey) -> str | None:
        return (await self._load(_key(key)))["state"]

    async def set_data(self, key: StorageKey, data: dict[str, Any]) -> None:
        row_key = _key(key)
        current = await self._load(row_key)
        await self._save(row_key, current["state"], dict(data))

    async def get_data(self, key: StorageKey) -> dict[str, Any]:
        return dict((await self._load(_key(key)))["data"])

    async def close(self) -> None:
        return None
