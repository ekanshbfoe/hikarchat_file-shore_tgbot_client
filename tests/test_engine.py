import asyncpg
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from bot.db.engine import Database, is_transient, normalize_database_url


@pytest.mark.parametrize(
    ("url", "expected", "ssl"),
    [
        ("postgres://u:p@h/db", "postgresql+asyncpg://u:p@h/db", False),
        ("postgresql://u:p@h/db", "postgresql+asyncpg://u:p@h/db", False),
        ("postgres://u:p@h/db?sslmode=require", "postgresql+asyncpg://u:p@h/db", True),
        (
            "postgresql://u:p@h/db?sslmode=require&channel_binding=require",
            "postgresql+asyncpg://u:p@h/db",
            True,
        ),
        ("postgres://u:p@h/db?sslmode=disable", "postgresql+asyncpg://u:p@h/db", False),
        ("postgresql+asyncpg://u:p@h/db", "postgresql+asyncpg://u:p@h/db", False),
        ("  postgres://u:p@h:6543/db?pgbouncer=true ", "postgresql+asyncpg://u:p@h:6543/db", False),
    ],
)
def test_any_url_style_is_accepted(url, expected, ssl):
    assert normalize_database_url(url) == (expected, ssl)


def test_connection_errors_are_transient_but_constraint_errors_are_not():
    assert is_transient(OSError("refused"))
    assert is_transient(TimeoutError())
    assert is_transient(asyncpg.CannotConnectNowError("waking"))
    assert not is_transient(IntegrityError("x", {}, Exception("dup")))
    assert not is_transient(ValueError("nope"))


async def test_read_works_against_real_database(db):
    async def op(conn):
        return (await conn.execute(text("select 1"))).scalar()

    assert await db.read(op) == 1


async def test_read_retries_while_database_wakes(db):
    calls = 0

    async def op(conn):
        nonlocal calls
        calls += 1
        if calls < 3:
            raise OSError("connection dropped while waking")
        return "ok"

    assert await db.read(op) == "ok"
    assert calls == 3


async def test_read_gives_up_after_all_retries(db):
    async def op(conn):
        raise OSError("still asleep")

    with pytest.raises(OSError):
        await db.read(op)


async def test_read_does_not_retry_real_errors(db):
    calls = 0

    async def op(conn):
        nonlocal calls
        calls += 1
        raise ValueError("bug")

    with pytest.raises(ValueError):
        await db.read(op)
    assert calls == 1


async def test_connect_retries_then_succeeds(db, monkeypatch):
    real_connect = db.engine.connect
    attempts = 0

    class Flaky:
        def connect(self):
            nonlocal attempts
            attempts += 1
            if attempts < 3:

                class Failing:
                    def __await__(self):
                        raise OSError("waking")
                        yield

                return Failing()
            return real_connect()

    real_engine = db.engine
    monkeypatch.setattr(
        db, "engine", type("E", (), {"connect": Flaky().connect, "dispose": real_engine.dispose})
    )
    async with db.write() as conn:
        assert (await conn.execute(text("select 1"))).scalar() == 1
    assert attempts == 3


async def test_write_rolls_back_on_failure(db):
    with pytest.raises(ValueError):
        async with db.write() as conn:
            await conn.execute(text("insert into settings(key, value) values ('a', '1')"))
            raise ValueError("boom")

    async def op(conn):
        return (await conn.execute(text("select count(*) from settings"))).scalar()

    assert await db.read(op) == 0


async def test_write_is_not_retried_after_statement_failure(db):
    runs = 0
    with pytest.raises(OSError):
        async with db.write():
            runs += 1
            raise OSError("dropped mid write")
    assert runs == 1


async def test_unreachable_database_raises_after_retries():
    database = Database("postgres://u:p@127.0.0.1:1/none", retry_delays=(0.01,))
    with pytest.raises(OSError):
        await database.read(lambda conn: conn.execute(text("select 1")))
    await database.close()
