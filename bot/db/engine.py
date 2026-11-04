"""Cloud Postgres access built to survive a scale-to-zero database.

Neon and Supabase can take several seconds to wake and may drop idle connections,
so every connection attempt is retried with backoff. Whole read operations are
retried too. Writes only retry the connection attempt, never the statement, so a
write cannot be applied twice.
"""

import asyncio
import logging
import ssl as ssl_module
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import TypeVar
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import uuid4

import asyncpg
from sqlalchemy.exc import DBAPIError, InterfaceError, OperationalError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

log = logging.getLogger(__name__)
T = TypeVar("T")

RETRY_DELAYS = (0.5, 1.0, 2.0, 4.0, 8.0)
CONNECT_TIMEOUT_SECONDS = 15
COMMAND_TIMEOUT_SECONDS = 30
# Below Neon's five minute idle suspend, so stale connections are replaced quietly.
POOL_RECYCLE_SECONDS = 240

_TRANSIENT_DRIVER_ERRORS = (
    asyncpg.PostgresConnectionError,
    asyncpg.CannotConnectNowError,
    asyncpg.TooManyConnectionsError,
    asyncpg.InterfaceError,
)
# Options understood by libpq URLs but not by asyncpg's connect().
_DROPPED_QUERY_KEYS = {"sslmode", "channel_binding", "pgbouncer", "connect_timeout", "options"}


def normalize_database_url(url: str) -> tuple[str, bool]:
    """Turn any postgres URL style into SQLAlchemy's form. Returns (url, use_ssl)."""
    parts = urlsplit(url.strip())
    query = parse_qsl(parts.query, keep_blank_values=True)
    sslmode = next((value for key, value in query if key == "sslmode"), None)
    use_ssl = sslmode not in (None, "disable", "allow", "prefer")
    kept = [(key, value) for key, value in query if key not in _DROPPED_QUERY_KEYS]
    return (
        urlunsplit(
            ("postgresql+asyncpg", parts.netloc, parts.path, urlencode(kept), parts.fragment)
        ),
        use_ssl,
    )


def build_engine(url: str) -> AsyncEngine:
    normalized, use_ssl = normalize_database_url(url)
    connect_args: dict = {
        "timeout": CONNECT_TIMEOUT_SECONDS,
        "command_timeout": COMMAND_TIMEOUT_SECONDS,
        # Poolers such as Neon's and Supabase's cannot track prepared statements.
        "statement_cache_size": 0,
        "prepared_statement_name_func": lambda: f"__asyncpg_{uuid4()}__",
    }
    if use_ssl:
        connect_args["ssl"] = ssl_module.create_default_context()
    return create_async_engine(
        normalized,
        pool_size=3,
        max_overflow=2,
        pool_timeout=30,
        pool_pre_ping=True,
        pool_recycle=POOL_RECYCLE_SECONDS,
        connect_args=connect_args,
    )


def is_transient(error: BaseException) -> bool:
    """True when the failure means the database was unreachable, not that it said no."""
    if isinstance(error, (OSError, TimeoutError, PoolTimeoutError, InterfaceError)):
        return True
    if isinstance(error, _TRANSIENT_DRIVER_ERRORS):
        return True
    if isinstance(error, OperationalError):
        return True
    if isinstance(error, DBAPIError):
        return error.connection_invalidated or isinstance(error.orig, _TRANSIENT_DRIVER_ERRORS)
    return False


class Database:
    def __init__(self, url: str, retry_delays: tuple[float, ...] = RETRY_DELAYS):
        self.engine = build_engine(url)
        self.retry_delays = retry_delays

    async def _connect(self) -> AsyncConnection:
        for delay in (*self.retry_delays, None):
            try:
                return await self.engine.connect()
            except Exception as error:
                if delay is None or not is_transient(error):
                    raise
                log.info("Database not reachable yet, retrying in %.1fs", delay)
                await asyncio.sleep(delay)
        raise AssertionError("unreachable")

    @asynccontextmanager
    async def write(self) -> AsyncIterator[AsyncConnection]:
        """A transaction. Only acquiring the connection is retried."""
        conn = await self._connect()
        try:
            async with conn.begin():
                yield conn
        finally:
            await conn.close()

    async def read(self, operation: Callable[[AsyncConnection], Awaitable[T]]) -> T:
        """Run a read-only operation, retrying all of it if the connection drops."""
        for delay in (*self.retry_delays, None):
            try:
                conn = await self._connect()
                try:
                    return await operation(conn)
                finally:
                    await conn.close()
            except Exception as error:
                if delay is None or not is_transient(error):
                    raise
                log.info("Database read interrupted, retrying in %.1fs", delay)
                await asyncio.sleep(delay)
        raise AssertionError("unreachable")

    async def close(self) -> None:
        await self.engine.dispose()
