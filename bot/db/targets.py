"""Force subscribe targets and who has satisfied them.

Each target has a version. A verification counts only while its version matches, so
changing or re-asking for one channel affects that channel and nothing else.
"""

from enum import StrEnum

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert

from bot.db.models import force_sub_targets as targets
from bot.db.models import verifications
from bot.db.store import LONG_TTL, SHORT_TTL, Store

TELEGRAM = "telegram"
YOUTUBE = "youtube"
TIKTOK = "tiktok"
SOCIAL = (YOUTUBE, TIKTOK)


class AddStatus(StrEnum):
    ADDED = "added"
    READDED = "readded"
    ALREADY = "already"


def _as_dict(row) -> dict:
    data = dict(row._mapping)
    data.pop("created_at", None)
    return data


class TargetsRepo:
    def __init__(self, store: Store):
        self.store = store

    async def list_active(self) -> list[dict]:
        async def loader(conn):
            rows = await conn.execute(
                select(targets).where(targets.c.is_active).order_by(targets.c.id)
            )
            return [_as_dict(row) for row in rows]

        return await self.store.read_through("targets", SHORT_TTL, loader)

    async def get(self, target_id: int) -> dict | None:
        async def loader(conn):
            row = (await conn.execute(select(targets).where(targets.c.id == target_id))).first()
            return _as_dict(row) if row else None

        return await self.store.db.read(loader)

    async def add(
        self,
        platform: str,
        identity: str,
        display_name: str,
        url: str | None,
        chat_id: int | None = None,
    ) -> tuple[dict, AddStatus]:
        async with self.store.db.write() as conn:
            result = await self._add(conn, platform, identity, display_name, url, chat_id)
        await self.store.cache.delete("targets")
        return result

    @staticmethod
    async def _add(conn, platform, identity, display_name, url, chat_id):
        existing = (
            await conn.execute(
                select(targets)
                .where(targets.c.platform == platform, targets.c.identity == identity)
                .with_for_update()
            )
        ).first()
        if existing is None:
            row = (
                await conn.execute(
                    targets.insert()
                    .values(
                        platform=platform,
                        identity=identity,
                        display_name=display_name,
                        url=url,
                        chat_id=chat_id,
                    )
                    .returning(targets)
                )
            ).first()
            return _as_dict(row), AddStatus.ADDED
        if existing.is_active:
            return _as_dict(existing), AddStatus.ALREADY
        # Same channel coming back: its version is untouched, so people stay verified.
        row = (
            await conn.execute(
                update(targets)
                .where(targets.c.id == existing.id)
                .values(is_active=True, display_name=display_name, url=url, chat_id=chat_id)
                .returning(targets)
            )
        ).first()
        return _as_dict(row), AddStatus.READDED

    async def replace(
        self, target_id: int, identity: str, display_name: str, url: str | None
    ) -> tuple[dict, AddStatus]:
        """Swap to a different channel: people must verify the new one."""
        async with self.store.db.write() as conn:
            old = (
                await conn.execute(
                    update(targets)
                    .where(targets.c.id == target_id)
                    .values(is_active=False)
                    .returning(targets.c.platform, targets.c.identity)
                )
            ).first()
            if old is None:
                raise LookupError(target_id)
            result = await self._add(conn, old.platform, identity, display_name, url, None)
        await self.store.cache.delete("targets")
        return result

    async def remove(self, target_id: int) -> None:
        await self._update(target_id, is_active=False)

    async def rename(self, target_id: int, display_name: str) -> None:
        await self._update(target_id, display_name=display_name)

    async def set_url(self, target_id: int, url: str) -> None:
        await self._update(target_id, url=url)

    async def ask_everyone_again(self, target_id: int) -> None:
        await self._update(target_id, version=targets.c.version + 1)

    async def _update(self, target_id: int, **values) -> None:
        async with self.store.db.write() as conn:
            await conn.execute(update(targets).where(targets.c.id == target_id).values(**values))
        await self.store.cache.delete("targets")

    async def migrate_chat(self, old_chat_id: int, new_chat_id: int) -> None:
        """A Telegram group upgraded to a supergroup and got a new id."""
        async with self.store.db.write() as conn:
            await conn.execute(
                update(targets)
                .where(targets.c.platform == TELEGRAM, targets.c.chat_id == old_chat_id)
                .values(chat_id=new_chat_id, identity=str(new_chat_id))
            )
        await self.store.cache.delete("targets")

    async def find_by_chat(self, chat_id: int) -> dict | None:
        for target in await self.list_active():
            if target["chat_id"] == chat_id:
                return target
        return None

    # --- verifications ---

    async def verified_versions(self, user_id: int) -> dict[str, int]:
        """target id (as text) -> version the user verified."""

        async def loader(conn):
            rows = await conn.execute(
                select(verifications.c.target_id, verifications.c.version).where(
                    verifications.c.user_id == user_id, verifications.c.verified
                )
            )
            return {str(row.target_id): row.version for row in rows}

        return await self.store.read_through(f"verified:{user_id}", LONG_TTL, loader)

    async def mark_verified(self, user_id: int, target: dict, method: str) -> None:
        values = {"version": target["version"], "method": method, "verified": True}
        statement = insert(verifications).values(user_id=user_id, target_id=target["id"], **values)
        async with self.store.db.write() as conn:
            await conn.execute(
                statement.on_conflict_do_update(
                    index_elements=[verifications.c.user_id, verifications.c.target_id],
                    set_={**values, "failed_attempts": 0},
                )
            )
        await self.store.cache.delete(f"verified:{user_id}")

    async def record_failure(self, user_id: int, target: dict) -> int:
        """Count a failed screenshot and return the running total for this version."""
        version = target["version"]
        statement = insert(verifications).values(
            user_id=user_id,
            target_id=target["id"],
            version=version,
            method="screenshot",
            verified=False,
            failed_attempts=1,
        )
        async with self.store.db.write() as conn:
            row = (
                await conn.execute(
                    statement.on_conflict_do_update(
                        index_elements=[verifications.c.user_id, verifications.c.target_id],
                        set_={
                            "failed_attempts": (verifications.c.failed_attempts + 1),
                        },
                        where=verifications.c.version == version,
                    ).returning(verifications.c.failed_attempts)
                )
            ).first()
            if row is not None:
                return row.failed_attempts
            # The attempts on record were for an earlier version of this channel.
            await conn.execute(
                update(verifications)
                .where(
                    verifications.c.user_id == user_id,
                    verifications.c.target_id == target["id"],
                )
                .values(version=version, verified=False, failed_attempts=1, method="screenshot")
            )
        await self.store.cache.delete(f"verified:{user_id}")
        return 1
