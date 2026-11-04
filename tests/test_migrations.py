from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import text

from bot.db.engine import build_engine
from bot.db.migrate import run_migrations
from bot.db.models import metadata
from tests.conftest import TEST_DATABASE_URL

MIGRATION_DB = TEST_DATABASE_URL.rsplit("/", 1)[0] + "/fsb_migration_check"


async def _recreate() -> None:
    admin = build_engine(TEST_DATABASE_URL).execution_options(isolation_level="AUTOCOMMIT")
    async with admin.connect() as conn:
        await conn.execute(text("DROP DATABASE IF EXISTS fsb_migration_check"))
        await conn.execute(text("CREATE DATABASE fsb_migration_check"))
    await admin.dispose()


async def test_migrations_produce_the_declared_schema():
    await _recreate()
    await run_migrations(MIGRATION_DB, attempts=1)
    await run_migrations(MIGRATION_DB, attempts=1)  # running twice must be harmless

    engine = build_engine(MIGRATION_DB)
    async with engine.connect() as conn:
        differences = await conn.run_sync(
            lambda sync: compare_metadata(MigrationContext.configure(sync), metadata)
        )
    await engine.dispose()
    assert differences == []
