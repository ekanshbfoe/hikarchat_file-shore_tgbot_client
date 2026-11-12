"""Owner, moderators and everybody else.

A moderator may be added by username before they have used the bot. Their id is
recorded at first contact and from then on only the id counts: renaming keeps access,
and someone else later taking the old username gets nothing.
"""

import re
from collections.abc import Iterable
from enum import StrEnum

from sqlalchemy import delete, select, update

from bot.db.models import roles, users
from bot.db.settings import SettingsRepo
from bot.db.store import SHORT_TTL, Store
from bot.db.users import clean_username

_USERNAME = re.compile(r"[a-z][a-z0-9_]{0,31}")


class Role(StrEnum):
    OWNER = "owner"
    MODERATOR = "moderator"
    USER = "user"


class AddResult(StrEnum):
    ADDED = "added"
    ALREADY = "already"
    IS_OWNER = "is_owner"
    INVALID = "invalid"


class RolesRepo:
    def __init__(self, store: Store, owner_id: int, extra_owner_ids: Iterable[int] = ()):
        self.store = store
        # The first one is who the bot reports problems to; all of them have its power.
        self.owner_id = owner_id
        self.owner_ids = frozenset({owner_id, *extra_owner_ids})

    def is_owner(self, user_id: int | None) -> bool:
        return user_id is not None and user_id in self.owner_ids

    async def resolve(self, user_id: int, username: str | None) -> Role:
        if self.is_owner(user_id):
            return Role.OWNER

        async def loader(conn):
            bound = (
                await conn.execute(select(roles.c.id).where(roles.c.user_id == user_id))
            ).scalar()
            return {"moderator": bound is not None}

        if (await self.store.read_through(f"role:{user_id}", SHORT_TTL, loader))["moderator"]:
            return Role.MODERATOR
        if await self._claim(user_id, clean_username(username)):
            return Role.MODERATOR
        return Role.USER

    async def _claim(self, user_id: int, username: str | None) -> bool:
        """Bind a moderator added by username to the person now holding that username."""
        if not username:
            return False
        found, unbound, fresh = await self.store.cache.get("unbound_moderators")
        if not (found and fresh):

            async def loader(conn):
                rows = await conn.execute(select(roles.c.username).where(roles.c.user_id.is_(None)))
                return [row.username for row in rows]

            unbound = await self.store.read_through("unbound_moderators", SHORT_TTL, loader)
        if username not in unbound:
            return False
        async with self.store.db.write() as conn:
            result = await conn.execute(
                update(roles)
                .where(roles.c.username == username, roles.c.user_id.is_(None))
                .values(user_id=user_id)
            )
        await self._invalidate()
        return result.rowcount > 0

    async def add_by_id(self, user_id: int, added_by: int) -> AddResult:
        """Add someone by their numeric user number, for people without a @username.
        The row is bound at once: only the number is known, and it never changes."""
        if self.is_owner(user_id):
            return AddResult.IS_OWNER
        if user_id <= 0:
            return AddResult.INVALID
        async with self.store.db.write() as conn:
            exists = (
                await conn.execute(select(roles.c.id).where(roles.c.user_id == user_id))
            ).scalar()
            if exists:
                return AddResult.ALREADY
            try:
                await conn.execute(
                    roles.insert().values(user_id=user_id, added_by=added_by)
                )
            except Exception:
                return AddResult.ALREADY  # A unique user_id means they are already in.
        await self._invalidate()
        return AddResult.ADDED

    async def add_by_username(self, username: str, added_by: int) -> AddResult:
        name = clean_username(username)
        if not name or not _USERNAME.fullmatch(name):
            return AddResult.INVALID
        async with self.store.db.write() as conn:
            known_id = (
                await conn.execute(select(users.c.id).where(users.c.username == name))
            ).scalar()
            if self.is_owner(known_id):
                return AddResult.IS_OWNER
            condition = roles.c.user_id == known_id if known_id else None
            exists = (
                await conn.execute(
                    select(roles.c.id).where(
                        roles.c.username == name
                        if condition is None
                        else condition | (roles.c.username == name)
                    )
                )
            ).scalar()
            if exists:
                return AddResult.ALREADY
            await conn.execute(
                roles.insert().values(user_id=known_id, username=name, added_by=added_by)
            )
        await self._invalidate()
        return AddResult.ADDED

    async def seed(self, usernames: list[str]) -> None:
        """Add usernames from the environment once only, so someone the owner later
        removes does not come back at the next restart."""
        settings = SettingsRepo(self.store)
        done = await settings.get("seeded_moderators", [])
        new = [name for name in usernames if name not in done]
        if not new:
            return
        for name in new:
            await self.add_by_username(name, self.owner_id)
        await settings.set("seeded_moderators", [*done, *new])

    async def list_moderators(self) -> list[dict]:
        async def loader(conn):
            rows = await conn.execute(
                select(roles.c.id, roles.c.user_id, roles.c.username, users.c.first_name)
                .select_from(roles.outerjoin(users, roles.c.user_id == users.c.id))
                .order_by(roles.c.id)
            )
            return [dict(row._mapping) for row in rows]

        return await self.store.db.read(loader)

    async def remove(self, role_id: int) -> tuple[bool, int | None]:
        """Returns (removed, user_id if known) so the caller can end open sessions."""
        async with self.store.db.write() as conn:
            row = (
                await conn.execute(
                    delete(roles).where(roles.c.id == role_id).returning(roles.c.user_id)
                )
            ).first()
        await self._invalidate()
        return (row is not None, row.user_id if row else None)

    async def _invalidate(self) -> None:
        await self.store.cache.delete_prefix("role:")
        await self.store.cache.delete("unbound_moderators")
