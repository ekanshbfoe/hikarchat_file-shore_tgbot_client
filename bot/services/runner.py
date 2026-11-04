"""Runs long jobs in the background and picks them up again after a restart."""

import asyncio
import logging

from bot.app import App
from bot.db.engine import is_transient

log = logging.getLogger(__name__)
RETRY_SECONDS = 30


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
                    level = logging.WARNING if is_transient(error) else logging.ERROR
                    log.log(level, "Job %s interrupted", job_id, exc_info=error)
                    if not is_transient(error):
                        await self.app.jobs.finish(job_id, "failed")
                        return
                    await asyncio.sleep(RETRY_SECONDS)
        finally:
            self._tasks.pop(job_id, None)

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
