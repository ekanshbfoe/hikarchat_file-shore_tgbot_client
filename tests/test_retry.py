import pytest
from aiogram.exceptions import TelegramRetryAfter, TelegramServerError
from aiogram.methods import GetMe, SendMessage

from bot import retry
from bot.retry import RetryMiddleware


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    slept = []

    async def sleep(seconds):
        slept.append(seconds)

    monkeypatch.setattr(retry.asyncio, "sleep", sleep)
    return slept


def flaky(*errors):
    remaining = list(errors)
    calls = []

    async def make_request(bot, method):
        calls.append(method)
        if remaining:
            raise remaining.pop(0)
        return "ok"

    return make_request, calls


METHOD = GetMe()


async def test_waits_as_told_then_retries(no_sleep):
    request, calls = flaky(TelegramRetryAfter(METHOD, "slow", 5))
    assert await RetryMiddleware()(request, None, METHOD) == "ok"
    assert len(calls) == 2 and no_sleep == [5.5]


async def test_long_wait_is_not_silently_absorbed():
    request, _ = flaky(TelegramRetryAfter(METHOD, "slow", 600))
    with pytest.raises(TelegramRetryAfter):
        await RetryMiddleware()(request, None, METHOD)


async def test_server_hiccup_is_retried():
    request, calls = flaky(TelegramServerError(METHOD, "bad"))
    assert await RetryMiddleware()(request, None, METHOD) == "ok"
    assert len(calls) == 2


async def test_gives_up_eventually():
    request, calls = flaky(*[TelegramServerError(METHOD, "bad")] * 9)
    with pytest.raises(TelegramServerError):
        await RetryMiddleware()(request, None, SendMessage(chat_id=1, text="x"))
    assert len(calls) == retry.MAX_ATTEMPTS
