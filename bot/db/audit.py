"""What each staff member did, kept so the owner can look back at it."""

import logging

from sqlalchemy import insert, select

from bot.db.models import staff_actions
from bot.db.store import Store

log = logging.getLogger(__name__)


class AuditRepo:
    def __init__(self, store: Store):
        self.store = store

    async def record(self, actor_id: int, action: str, **details) -> None:
        """One line of history. A missed line must never break the person's action."""
        try:
            async with self.store.db.write() as conn:
                await conn.execute(
                    insert(staff_actions).values(actor_id=actor_id, action=action, details=details)
                )
        except Exception:
            log.warning("Could not record staff action %s", action, exc_info=True)

    async def recent(self, actor_id: int, limit: int = 15) -> list[dict]:
        """Newest first."""

        async def loader(conn):
            rows = await conn.execute(
                select(
                    staff_actions.c.action,
                    staff_actions.c.details,
                    staff_actions.c.created_at,
                )
                .where(staff_actions.c.actor_id == actor_id)
                .order_by(staff_actions.c.id.desc())
                .limit(limit)
            )
            return [dict(row._mapping) for row in rows]

        return await self.store.db.read(loader)
