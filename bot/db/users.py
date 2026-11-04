"""Users, bans and the link a user is waiting for."""

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert

from bot.db.models import users
from bot.db.store import SHORT_TTL, Store

SEEN_TTL = 3600.0


def clean_username(username: str | None) -> str | None:
    return username.strip().lstrip("@").lower() or None if username else None


class UsersRepo:
    def __init__(self, store: Store):
        self.store = store

    async def touch(self, user_id: int, username: str | None, first_name: str | None) -> None:
        """Record a user. Skips the cloud when nothing changed recently."""
        username = clean_username(username)
        fingerprint = [username, first_name]
        found, value, fresh = await self.store.cache.get(f"seen:{user_id}")
        if found and fresh and value == fingerprint:
            return
        values = {"id": user_id, "username": username, "first_name": first_name}
        statement = insert(users).values(**values)
        async with self.store.db.write() as conn:
            await conn.execute(
                statement.on_conflict_do_update(
                    index_elements=[users.c.id],
                    # Writing to the bot again means they have unblocked it.
                    set_={"username": username, "first_name": first_name, "is_active": True},
                )
            )
        await self.store.cache.set(f"seen:{user_id}", fingerprint, SEEN_TTL)

    async def find_id_by_username(self, username: str) -> int | None:
        name = clean_username(username)

        async def loader(conn):
            return (await conn.execute(select(users.c.id).where(users.c.username == name))).scalar()

        return await self.store.db.read(loader)

    async def exists(self, user_id: int) -> bool:
        async def loader(conn):
            return (
                await conn.execute(select(users.c.id).where(users.c.id == user_id))
            ).scalar() is not None

        return await self.store.db.read(loader)

    async def is_banned(self, user_id: int) -> bool:
        async def loader(conn):
            banned = (
                await conn.execute(select(users.c.is_banned).where(users.c.id == user_id))
            ).scalar()
            return bool(banned)

        return await self.store.read_through(f"banned:{user_id}", SHORT_TTL, loader)

    async def set_banned(self, user_id: int, banned: bool) -> None:
        statement = insert(users).values(id=user_id, is_banned=banned)
        async with self.store.db.write() as conn:
            await conn.execute(
                statement.on_conflict_do_update(
                    index_elements=[users.c.id], set_={"is_banned": banned}
                )
            )
        await self.store.cache.set(f"banned:{user_id}", banned, SHORT_TTL)

    async def deactivate(self, user_id: int) -> None:
        async with self.store.db.write() as conn:
            await conn.execute(update(users).where(users.c.id == user_id).values(is_active=False))
        await self.store.cache.delete(f"seen:{user_id}")

    async def get_pending(self, user_id: int) -> str | None:
        async def loader(conn):
            return (
                await conn.execute(select(users.c.pending_code).where(users.c.id == user_id))
            ).scalar()

        return await self.store.db.read(loader)

    async def set_pending(self, user_id: int, code: str | None) -> None:
        async with self.store.db.write() as conn:
            await conn.execute(update(users).where(users.c.id == user_id).values(pending_code=code))

    async def count_reachable(self) -> int:
        async def loader(conn):
            return (
                await conn.execute(
                    select(func.count())
                    .select_from(users)
                    .where(users.c.is_active, users.c.is_banned.is_(False))
                )
            ).scalar()

        return await self.store.db.read(loader)

    async def reachable_after(self, cursor: int, limit: int = 200) -> list[int]:
        """Ids to broadcast to, in a stable order so a broadcast can resume."""

        async def loader(conn):
            rows = await conn.execute(
                select(users.c.id)
                .where(users.c.id > cursor, users.c.is_active, users.c.is_banned.is_(False))
                .order_by(users.c.id)
                .limit(limit)
            )
            return [row.id for row in rows]

        return await self.store.db.read(loader)
