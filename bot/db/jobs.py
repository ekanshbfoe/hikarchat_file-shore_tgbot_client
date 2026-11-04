"""Long-running work (broadcasts, batches) that must resume after a restart."""

from sqlalchemy import select, update

from bot.db.models import jobs
from bot.db.store import Store

RUNNING = "running"
DONE = "done"
CANCELLED = "cancelled"
FAILED = "failed"


class JobsRepo:
    def __init__(self, store: Store):
        self.store = store

    async def create(self, kind: str, created_by: int, payload: dict, cursor: int = 0) -> int:
        async with self.store.db.write() as conn:
            return (
                await conn.execute(
                    jobs.insert()
                    .values(kind=kind, created_by=created_by, payload=payload, cursor=cursor)
                    .returning(jobs.c.id)
                )
            ).scalar()

    async def get(self, job_id: int) -> dict | None:
        async def loader(conn):
            row = (await conn.execute(select(jobs).where(jobs.c.id == job_id))).first()
            return dict(row._mapping) if row else None

        return await self.store.db.read(loader)

    async def running(self, kind: str | None = None) -> list[dict]:
        async def loader(conn):
            query = select(jobs).where(jobs.c.status == RUNNING).order_by(jobs.c.id)
            if kind:
                query = query.where(jobs.c.kind == kind)
            return [dict(row._mapping) for row in await conn.execute(query)]

        return await self.store.db.read(loader)

    async def save_progress(self, job_id: int, cursor: int, stats: dict) -> None:
        async with self.store.db.write() as conn:
            await conn.execute(
                update(jobs).where(jobs.c.id == job_id).values(cursor=cursor, stats=stats)
            )

    async def finish(self, job_id: int, status: str) -> None:
        async with self.store.db.write() as conn:
            await conn.execute(update(jobs).where(jobs.c.id == job_id).values(status=status))

    async def is_cancelled(self, job_id: int) -> bool:
        async def loader(conn):
            status = (await conn.execute(select(jobs.c.status).where(jobs.c.id == job_id))).scalar()
            return status == CANCELLED

        return await self.store.db.read(loader)
