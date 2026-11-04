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


class World:
    """A running bot with people to talk to it."""

    def __init__(self, app, dispatcher, session):
        from tests.helpers import OWNER_ID

        self.app = app
        self.dispatcher = dispatcher
        self.telegram = session
        self.owner = self.person(OWNER_ID, "owner_name")

    def person(self, user_id, username=None):
        from tests.fake_telegram import Chatter

        return Chatter(self.dispatcher, self.app.bot, user_id, username)


@pytest.fixture(autouse=True)
def _no_pacing(monkeypatch):
    from bot.services import batch, delivery

    monkeypatch.setattr(delivery, "PACE_SECONDS", 0)
    monkeypatch.setattr(batch, "PACE_SECONDS", 0)


@pytest.fixture
async def world(db, tmp_path):
    from bot.app import App
    from bot.config import Settings
    from bot.dispatcher import build_dispatcher
    from tests.fake_telegram import FakeSession, make_bot
    from tests.helpers import OWNER_ID, open_cache

    config = Settings(
        _env_file=None,
        bot_token="42:TEST",
        owner_id=OWNER_ID,
        backup_channel_id=-100500,
        database_url=TEST_DATABASE_URL,
        dev_chat_id=None,
    )
    cache = await open_cache(tmp_path / "world.sqlite3")
    session = FakeSession()
    bot = make_bot(session)
    await bot.me()
    session.clear()
    app = App(config=config, bot=bot, store=Store(db, cache))
    dispatcher = build_dispatcher(app)
    yield World(app, dispatcher, session)
    await app.runner.stop()
    # Routers are module level and may only have one parent.
    for router in dispatcher.sub_routers:
        router._parent_router = None
    await cache.close()
