"""Telegram sometimes asks us to slow down, or has a brief hiccup. Handle both here so
no handler has to think about it."""

import asyncio
import logging

from aiogram import Bot
from aiogram.client.session.middlewares.base import BaseRequestMiddleware, NextRequestMiddlewareType
from aiogram.exceptions import TelegramNetworkError, TelegramRetryAfter, TelegramServerError
from aiogram.methods import Response, TelegramMethod
from aiogram.methods.base import TelegramType

log = logging.getLogger(__name__)
MAX_ATTEMPTS = 4
# A person is waiting on most calls, so don't sit silently for minutes. Long pauses
# surface to the caller, and background jobs have their own patience on top of this.
MAX_WAIT_SECONDS = 60


class RetryMiddleware(BaseRequestMiddleware):
    async def __call__(
        self,
        make_request: NextRequestMiddlewareType[TelegramType],
        bot: Bot,
        method: TelegramMethod[TelegramType],
    ) -> Response[TelegramType]:
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                return await make_request(bot, method)
            except TelegramRetryAfter as error:
                if attempt == MAX_ATTEMPTS or error.retry_after > MAX_WAIT_SECONDS:
                    raise
                log.info("Telegram asked to wait %ss", error.retry_after)
                await asyncio.sleep(error.retry_after + 0.5)
            except (TelegramServerError, TelegramNetworkError):
                if attempt == MAX_ATTEMPTS:
                    raise
                await asyncio.sleep(attempt)
        raise AssertionError("unreachable")
