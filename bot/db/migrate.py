"""Run database migrations, waiting for a sleeping database to wake up."""

import asyncio
import logging
from pathlib import Path

from alembic import command
from alembic.config import Config

from bot.db.engine import is_transient

log = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[2]


def _upgrade(url: str) -> None:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.attributes["url"] = url
    command.upgrade(config, "head")


async def run_migrations(url: str, attempts: int = 10, delay: float = 5.0) -> None:
    for attempt in range(1, attempts + 1):
        try:
            # Alembic's env.py starts its own event loop, so it needs its own thread.
            await asyncio.to_thread(_upgrade, url)
            return
        except Exception as error:
            if attempt == attempts or not is_transient(error):
                raise
            log.info("Waiting for the database before migrating (attempt %d)", attempt)
            await asyncio.sleep(delay)
