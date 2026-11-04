"""Sends one message to every reachable user. Progress is saved after each person, so
after a restart it continues where it stopped with at most one repeated message."""

import asyncio
import logging
import time

from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramRetryAfter,
)
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot import texts
from bot.app import App
from bot.db.jobs import DONE, FAILED

log = logging.getLogger(__name__)
KIND = "broadcast"
# Telegram's guidance is about 30 messages a second. Stay well inside it.
PACE_SECONDS = 0.05
PROGRESS_EVERY_SECONDS = 5.0
CANCEL_CHECK_EVERY = 20

_SOURCE_GONE = ("message to copy not found", "message can't be copied", "message_id_invalid")
_USER_GONE = ("chat not found", "user is deactivated", "bot was blocked", "peer_id_invalid")


class SourceGoneError(Exception):
    pass


def _stop_markup(job_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=texts.BROADCAST_STOP, callback_data=f"bc:stop:{job_id}")]
        ]
    )


async def _say(app: App, job: dict, text: str, markup=None) -> None:
    payload = job["payload"]
    try:
        await app.bot.edit_message_text(
            text=text,
            chat_id=payload["chat_id"],
            message_id=payload["progress_id"],
            reply_markup=markup,
        )
    except (TelegramBadRequest, TelegramForbiddenError):
        log.debug("Could not update broadcast progress")


async def _send(app: App, user_id: int, payload: dict) -> bool:
    """Returns whether this person received it."""
    while True:
        try:
            await app.bot.copy_message(
                chat_id=user_id,
                from_chat_id=payload["chat_id"],
                message_id=payload["message_id"],
            )
            return True
        except TelegramRetryAfter as error:
            await asyncio.sleep(error.retry_after + 1)
        except TelegramForbiddenError:
            await app.users.deactivate(user_id)
            return False
        except TelegramBadRequest as error:
            problem = str(error).lower()
            if any(text in problem for text in _SOURCE_GONE):
                raise SourceGoneError from error
            if any(text in problem for text in _USER_GONE):
                await app.users.deactivate(user_id)
            return False


async def run(app: App, job: dict) -> None:
    job_id, payload = job["id"], job["payload"]
    cursor = job["cursor"]
    sent = job["stats"].get("sent", 0)
    failed = job["stats"].get("failed", 0)
    last_report = time.monotonic()
    since_check = 0

    while True:
        user_ids = await app.users.reachable_after(cursor)
        if not user_ids:
            break
        for user_id in user_ids:
            since_check += 1
            if since_check >= CANCEL_CHECK_EVERY:
                since_check = 0
                if await app.jobs.is_cancelled(job_id):
                    await _say(app, job, texts.BROADCAST_STOPPED.format(sent=sent, failed=failed))
                    app.log.post(texts.LOG_BROADCAST_STOPPED.format(sent=sent, failed=failed))
                    return
            try:
                received = await _send(app, user_id, payload)
            except SourceGoneError:
                await app.jobs.finish(job_id, FAILED)
                await _say(app, job, texts.BROADCAST_SOURCE_GONE.format(sent=sent))
                app.log.post(texts.LOG_BROADCAST_STOPPED.format(sent=sent, failed=failed))
                return
            sent, failed = (sent + 1, failed) if received else (sent, failed + 1)
            cursor = user_id
            await app.jobs.save_progress(job_id, cursor, {"sent": sent, "failed": failed})
            if time.monotonic() - last_report >= PROGRESS_EVERY_SECONDS:
                last_report = time.monotonic()
                await _say(
                    app, job, texts.BROADCAST_PROGRESS.format(sent=sent), _stop_markup(job_id)
                )
            await asyncio.sleep(PACE_SECONDS)

    if await app.jobs.is_cancelled(job_id):
        await _say(app, job, texts.BROADCAST_STOPPED.format(sent=sent, failed=failed))
        app.log.post(texts.LOG_BROADCAST_STOPPED.format(sent=sent, failed=failed))
        return
    await app.jobs.finish(job_id, DONE)
    await _say(app, job, texts.BROADCAST_DONE.format(sent=sent, failed=failed))
    app.log.post(texts.LOG_BROADCAST_DONE.format(sent=sent, failed=failed))
