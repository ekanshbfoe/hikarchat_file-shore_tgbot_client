"""Alembic environment. The URL comes from DATABASE_DIRECT_URL or DATABASE_URL."""

import asyncio
import os

from alembic import context
from sqlalchemy.ext.asyncio import AsyncEngine

from bot.db.engine import build_engine
from bot.db.models import metadata


def _url() -> str:
    url = (
        context.config.attributes.get("url")
        or os.environ.get("DATABASE_DIRECT_URL")
        or os.environ.get("DATABASE_URL")
    )
    if not url:
        raise RuntimeError("DATABASE_URL must be set")
    return url


def _run(connection) -> None:
    context.configure(connection=connection, target_metadata=metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def _run_online() -> None:
    engine: AsyncEngine = build_engine(_url())
    async with engine.connect() as connection:
        await connection.run_sync(_run)
        await connection.commit()
    await engine.dispose()


asyncio.run(_run_online())
