import pytest

from bot.db.local_cache import LocalCache
from bot.db.store import Store


class FakeDb:
    def __init__(self):
        self.value = "cloud"
        self.calls = 0
        self.error = None

    async def read(self, loader):
        self.calls += 1
        if self.error:
            raise self.error
        return await loader(None)


@pytest.fixture
async def store(tmp_path):
    cache = LocalCache(str(tmp_path / "c.sqlite3"))
    await cache.open()
    yield Store(FakeDb(), cache)
    await cache.close()


def loader_for(store):
    async def loader(_):
        return store.db.value

    return loader


async def test_second_read_comes_from_local(store):
    assert await store.read_through("k", 60, loader_for(store)) == "cloud"
    assert await store.read_through("k", 60, loader_for(store)) == "cloud"
    assert store.db.calls == 1


async def test_expired_entry_goes_back_to_cloud(store):
    await store.read_through("k", -1, loader_for(store))
    store.db.value = "newer"
    assert await store.read_through("k", 60, loader_for(store)) == "newer"
    assert store.db.calls == 2


async def test_not_found_is_never_cached(store):
    store.db.value = None
    assert await store.read_through("k", 60, loader_for(store)) is None
    store.db.value = "created now"
    assert await store.read_through("k", 60, loader_for(store)) == "created now"


async def test_not_found_is_cached_when_the_caller_asks(store):
    store.db.value = None
    assert await store.read_through("k", 60, loader_for(store), none_ttl=60) is None
    store.db.value = "created now"
    assert await store.read_through("k", 60, loader_for(store), none_ttl=60) is None
    assert store.db.calls == 1


async def test_cloud_outage_uses_expired_copy(store):
    await store.read_through("k", -1, loader_for(store))
    store.db.error = OSError("down")
    assert await store.read_through("k", 60, loader_for(store)) == "cloud"


async def test_cloud_outage_without_local_copy_raises(store):
    store.db.error = OSError("down")
    with pytest.raises(OSError):
        await store.read_through("k", 60, loader_for(store))


async def test_real_errors_are_not_hidden_by_expired_copy(store):
    await store.read_through("k", -1, loader_for(store))
    store.db.error = ValueError("bug")
    with pytest.raises(ValueError):
        await store.read_through("k", 60, loader_for(store))
