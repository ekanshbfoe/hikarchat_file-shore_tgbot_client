import pytest

from bot.db.local_cache import LocalCache


@pytest.fixture
async def cache(tmp_path):
    local = LocalCache(str(tmp_path / "cache.sqlite3"))
    await local.open()
    yield local
    await local.close()


async def test_set_and_get(cache):
    await cache.set("a", {"x": 1}, 60)
    assert await cache.get("a") == (True, {"x": 1}, True)


async def test_missing_key(cache):
    assert await cache.get("nope") == (False, None, False)


async def test_expired_entry_is_returned_as_stale(cache):
    await cache.set("a", 1, -1)
    assert await cache.get("a") == (True, 1, False)


async def test_delete_and_prefix(cache):
    await cache.set("user:1", 1, 60)
    await cache.set("user:2", 2, 60)
    await cache.set("user_3", 3, 60)
    await cache.delete("user:1")
    assert (await cache.get("user:1"))[0] is False
    await cache.delete_prefix("user:")
    assert (await cache.get("user:2"))[0] is False
    assert (await cache.get("user_3"))[0] is True


async def test_prefix_treats_wildcards_literally(cache):
    await cache.set("a_b", 1, 60)
    await cache.set("axb", 2, 60)
    await cache.delete_prefix("a_")
    assert (await cache.get("axb"))[0] is True


async def test_corrupt_file_is_recreated(tmp_path):
    path = tmp_path / "broken.sqlite3"
    path.write_bytes(b"this is not a database" * 100)
    local = LocalCache(str(path))
    await local.open()
    await local.set("a", 1, 60)
    assert (await local.get("a"))[1] == 1
    await local.close()


async def test_unusable_path_never_raises(tmp_path):
    local = LocalCache(str(tmp_path / "no" / "such" / "dir" / "c.sqlite3"))
    await local.open()
    await local.set("a", 1, 60)
    await local.delete("a")
    await local.delete_prefix("a")
    assert await local.get("a") == (False, None, False)
    await local.close()


async def test_file_corrupted_while_running_recovers(tmp_path):
    local = LocalCache(str(tmp_path / "c.sqlite3"))
    await local.open()
    await local._conn.close()  # simulate the connection breaking underneath us
    assert await local.get("a") == (False, None, False)
    await local.set("a", 1, 60)
    assert (await local.get("a"))[1] == 1
    await local.close()
