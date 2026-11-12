import pytest
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.base import StorageKey

from bot.db.fsm_storage import PostgresStorage
from bot.db.local_cache import LocalCache
from bot.db.store import Store

KEY = StorageKey(bot_id=1, chat_id=2, user_id=3)


class Form(StatesGroup):
    waiting = State()


async def make_cache(tmp_path, name="c.sqlite3"):
    cache = LocalCache(str(tmp_path / name))
    await cache.open()
    return cache


@pytest.fixture
async def storage(db, tmp_path):
    cache = await make_cache(tmp_path)
    yield PostgresStorage(Store(db, cache))
    await cache.close()


async def test_defaults_are_empty(storage):
    assert await storage.get_state(KEY) is None
    assert await storage.get_data(KEY) == {}


async def test_state_and_data_round_trip(storage):
    await storage.set_state(KEY, Form.waiting)
    await storage.set_data(KEY, {"items": [1, 2]})
    assert await storage.get_state(KEY) == "Form:waiting"
    assert await storage.get_data(KEY) == {"items": [1, 2]}


async def test_conversation_survives_restart_with_wiped_disk(db, tmp_path):
    first = await make_cache(tmp_path, "one.sqlite3")
    await PostgresStorage(Store(db, first)).set_state(KEY, Form.waiting)
    await PostgresStorage(Store(db, first)).set_data(KEY, {"code": "x"})
    await first.close()

    wiped = await make_cache(tmp_path, "two.sqlite3")
    fresh = PostgresStorage(Store(db, wiped))
    assert await fresh.get_state(KEY) == "Form:waiting"
    assert await fresh.get_data(KEY) == {"code": "x"}
    await wiped.close()


async def test_clearing_removes_the_row(storage):
    await storage.set_state(KEY, Form.waiting)
    await storage.set_data(KEY, {"a": 1})
    await storage.set_state(KEY, None)
    await storage.set_data(KEY, {})
    assert await storage.get_state(KEY) is None
    assert await storage.get_data(KEY) == {}


async def test_asking_twice_about_a_missing_session_asks_the_cloud_once(storage, monkeypatch):
    reads = 0
    real = storage.store.db.read

    async def counting(operation):
        nonlocal reads
        reads += 1
        return await real(operation)

    monkeypatch.setattr(storage.store.db, "read", counting)
    assert await storage.get_state(KEY) is None
    assert await storage.get_state(KEY) is None
    assert reads == 1


async def test_clearing_a_session_that_never_existed_writes_nothing(storage, monkeypatch):
    writes = 0
    real = storage.store.db.write

    def counting():
        nonlocal writes
        writes += 1
        return real()

    monkeypatch.setattr(storage.store.db, "write", counting)
    await storage.set_state(KEY, None)
    await storage.set_data(KEY, {})
    assert writes == 0
