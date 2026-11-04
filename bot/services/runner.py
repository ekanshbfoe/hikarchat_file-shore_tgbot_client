"""Runs long jobs in the background and picks them up again after a restart."""

import asyncio
import logging

from aiogram.exceptions import (
    TelegramNetworkError,
    TelegramRetryAfter,
    TelegramServerError,
)

from bot import texts
from bot.app import App
from bot.db.engine import is_transient

log = logging.getLogger(__name__)
RETRY_SECONDS = 30


def _wait_before_retry(error: Exception) -> float | None:
    """How long to wait if this trouble is temporary, otherwise None."""
    if isinstance(error, TelegramRetryAfter):
        return error.retry_after + 1
    if isinstance(error, (TelegramNetworkError, TelegramServerError)) or is_transient(error):
        return RETRY_SECONDS
    return None


class JobRunner:
    def __init__(self, app: App):
        self.app = app
        self.handlers: dict[str, callable] = {}
        self._tasks: dict[int, asyncio.Task] = {}

    def register(self, kind: str, handler) -> None:
        self.handlers[kind] = handler

    def start(self, job_id: int, kind: str) -> None:
        if job_id in self._tasks:
            return
        self._tasks[job_id] = asyncio.create_task(self._run(job_id, kind))

    async def _run(self, job_id: int, kind: str) -> None:
        try:
            while True:
                try:
                    job = await self.app.jobs.get(job_id)
                    if job is None or job["status"] != "running":
                        return
                    await self.handlers[kind](self.app, job)
                    return
                except asyncio.CancelledError:
                    raise
                except Exception as error:
                    # A brief outage shouldn't end a broadcast half way. Try again.
                    wait = _wait_before_retry(error)
                    if wait is None:
                        log.error("Job %s failed", job_id, exc_info=error)
                        await self._give_up(job_id)
                        return
                    log.warning("Job %s interrupted, retrying in %ss", job_id, wait)
                    await asyncio.sleep(wait)
        finally:
            self._tasks.pop(job_id, None)

    async def _give_up(self, job_id: int) -> None:
        try:
            job = await self.app.jobs.get(job_id)
            await self.app.jobs.finish(job_id, "failed")
            await self.app.bot.send_message(job["payload"]["chat_id"], texts.SOMETHING_WRONG)
        except Exception:
            log.exception("Could not report job %s", job_id)

    async def resume_all(self) -> None:
        for job in await self.app.jobs.running():
            if job["kind"] in self.handlers:
                self.start(job["id"], job["kind"])

    async def wait(self) -> None:
        """For tests: wait until everything has finished."""
        while self._tasks:
            await asyncio.gather(*list(self._tasks.values()), return_exceptions=True)

    async def stop(self) -> None:
        for task in list(self._tasks.values()):
            task.cancel()
        await asyncio.gather(*list(self._tasks.values()), return_exceptions=True)
