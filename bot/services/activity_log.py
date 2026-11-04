"""Posts activity to the client's logs group.

Telegram allows a bot about 20 messages a minute in a group, so everything goes through
a paced background queue. Nobody ever waits for a log line, and a problem here is never
anyone's problem but the logs': it can't stop a file being delivered.
"""

import asyncio
import itertools
import logging
from collections.abc import Awaitable, Callable

from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramMigrateToChat,
    TelegramRetryAfter,
)
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, User

from bot import texts
from bot.services.notices import notify_owner_once

log = logging.getLogger(__name__)
PACE_SECONDS = 3.1
MAX_QUEUED = 500
_REVIEW, _NORMAL = 0, 1  # A review someone must act on goes ahead of ordinary lines.
CHAT_OVERRIDE = "log_chat_id"
_PLATFORM_NAMES = {
    "telegram": texts.FS_PLATFORM_TELEGRAM,
    "youtube": texts.FS_PLATFORM_YOUTUBE,
    "tiktok": texts.FS_PLATFORM_TIKTOK,
}


def platform_name(target: dict) -> str:
    return _PLATFORM_NAMES[target["platform"]]


def actor(user: User) -> str:
    return texts.LOG_ACTOR.format(name=texts.esc(user.full_name), user_id=user.id)


def review_markup(user_id: int, target_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=texts.REVIEW_APPROVE, callback_data=f"rv:ok:{user_id}:{target_id}"
                ),
                InlineKeyboardButton(
                    text=texts.REVIEW_REJECT, callback_data=f"rv:no:{user_id}:{target_id}"
                ),
            ]
        ]
    )


class ActivityLog:
    def __init__(self, app):
        self.app = app
        self._queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
        self._order = itertools.count()
        self._worker: asyncio.Task | None = None

    @property
    def enabled(self) -> bool:
        return self.app.config.log_chat_id is not None

    async def chat_id(self) -> int:
        """A group upgraded to a supergroup gets a new id, remembered in settings."""
        return await self.app.settings.get(CHAT_OVERRIDE, self.app.config.log_chat_id)

    def _enqueue(self, priority: int, send: Callable[[int], Awaitable[None]]) -> None:
        if not self.enabled:
            return
        if priority == _NORMAL and self._queue.qsize() >= MAX_QUEUED:
            log.warning("Logs group queue is full; dropping a line")
            return
        self._queue.put_nowait((priority, next(self._order), send))

    def post(self, text: str) -> None:
        async def send(chat_id: int) -> None:
            await self.app.bot.send_message(chat_id, text, disable_web_page_preview=True)

        self._enqueue(_NORMAL, send)

    def review(self, message: Message, target: dict, attempts: int) -> None:
        """Show staff the screenshot of someone let through, with buttons to decide."""
        user = message.from_user
        caption = texts.REVIEW_CAPTION.format(
            actor=actor(user),
            name=texts.esc(target["display_name"]),
            platform=platform_name(target),
            attempts=attempts,
        )
        markup = review_markup(user.id, target["id"])

        async def send(chat_id: int) -> None:
            try:
                await self.app.bot.copy_message(
                    chat_id,
                    from_chat_id=message.chat.id,
                    message_id=message.message_id,
                    caption=caption,
                    reply_markup=markup,
                )
            except TelegramBadRequest as error:
                if "chat not found" in str(error).lower():
                    raise
                # They deleted the picture already. Staff can still decide.
                await self.app.bot.send_message(
                    chat_id, caption + texts.REVIEW_NO_PICTURE, reply_markup=markup
                )

        self._enqueue(_REVIEW, send)

    async def _deliver(self, send: Callable[[int], Awaitable[None]]) -> None:
        for _ in range(3):
            try:
                await send(await self.chat_id())
                return
            except TelegramMigrateToChat as error:
                await self.app.settings.set(CHAT_OVERRIDE, error.migrate_to_chat_id)
            except TelegramRetryAfter as error:
                await asyncio.sleep(error.retry_after + 1)
            except (TelegramForbiddenError, TelegramBadRequest):
                log.warning("Could not post to the logs group", exc_info=True)
                await self._tell_owner()
                return

    async def _tell_owner(self) -> None:
        await notify_owner_once(self.app, "log_chat", texts.LOG_CHAT_NOTICE)

    async def check_access(self) -> bool:
        if not self.enabled:
            return True
        try:
            member = await self.app.bot.get_chat_member(await self.chat_id(), self.app.bot.id)
            allowed = member.status not in ("left", "kicked")
        except TelegramMigrateToChat as error:
            await self.app.settings.set(CHAT_OVERRIDE, error.migrate_to_chat_id)
            return True
        except (TelegramBadRequest, TelegramForbiddenError):
            allowed = False
        if not allowed:
            await self._tell_owner()
        return allowed

    async def _work(self) -> None:
        while True:
            _, _, send = await self._queue.get()
            try:
                await self._deliver(send)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.warning("Could not post to the logs group", exc_info=True)
            finally:
                self._queue.task_done()
            await asyncio.sleep(PACE_SECONDS)

    def start(self) -> None:
        if self._worker is None:
            self._worker = asyncio.create_task(self._work())

    async def stop(self) -> None:
        if self._worker is not None:
            self._worker.cancel()
            await asyncio.gather(self._worker, return_exceptions=True)
            self._worker = None

    async def drain(self) -> None:
        """For tests: wait until everything queued has been sent."""
        await self._queue.join()
