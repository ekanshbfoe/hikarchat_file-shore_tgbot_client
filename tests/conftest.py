import asyncio
import os

import pytest
from sqlalchemy import text

from bot.db.engine import Database, build_engine
from bot.db.models import metadata
from bot.db.store import Store

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgres://postgres:test@localhost:55432/fsb_test"
)


@pytest.fixture(scope="session", autouse=True)
def _schema():
    async def create():
        engine = build_engine(TEST_DATABASE_URL)
        async with engine.begin() as conn:
            await conn.run_sync(metadata.drop_all)
            await conn.run_sync(metadata.create_all)
        await engine.dispose()

    asyncio.run(create())


@pytest.fixture
async def db():
    database = Database(TEST_DATABASE_URL, retry_delays=(0.01, 0.01))
    async with database.write() as conn:
        tables = ", ".join(table.name for table in metadata.sorted_tables)
        await conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    yield database
    await database.close()


@pytest.fixture
async def repos(db, tmp_path):
    from tests.helpers import Repos, open_cache

    cache = await open_cache(tmp_path / "cache.sqlite3")
    yield Repos(Store(db, cache))
    await cache.close()
