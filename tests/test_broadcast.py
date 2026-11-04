from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramRetryAfter,
)
from aiogram.methods import AnswerCallbackQuery, CopyMessage
from aiogram.types import Invoice, MessageId

from bot import texts
from bot.services import broadcast as service
from tests.fake_telegram import button_data
from tests.helpers import OWNER_ID


async def add_users(world, *ids):
    for user_id in ids:
        await world.app.users.touch(user_id, None, None)


async def start_broadcast(world, wait=True):
    await world.owner.send("/broadcast")
    source = await world.owner.send("news")
    data = button_data(world.telegram.last_markup(OWNER_ID))
    await world.owner.tap(data[0])
    if wait:
        await world.app.runner.wait()
    return source


def targets(world):
    return [c.chat_id for c in world.telegram.of(CopyMessage)]


async def test_full_flow_with_preview(world):
    await add_users(world, 1, 2, 3)
    await world.owner.send("/broadcast")
    await world.owner.send("news")
    # Before confirming, only the sender has it.
    assert targets(world) == [OWNER_ID]
    assert "4 user" in world.telegram.last_text(OWNER_ID)
    await world.owner.tap(button_data(world.telegram.last_markup(OWNER_ID))[0])
    await world.app.runner.wait()
    assert sorted(targets(world)[1:]) == [1, 2, 3, OWNER_ID]
    assert world.telegram.last_text(OWNER_ID) == texts.BROADCAST_DONE.format(sent=4, failed=0)


async def test_cancelling_preview_sends_nothing(world):
    await add_users(world, 1)
    await world.owner.send("/broadcast")
    await world.owner.send("news")
    await world.owner.tap("cancel")
    await world.app.runner.wait()
    assert targets(world) == [OWNER_ID]


async def test_reply_form(world):
    source = await world.owner.send("old news")
    world.telegram.clear()
    await world.owner.send("/broadcast", reply_to_message=source)
    assert targets(world) == [OWNER_ID]


async def test_uncopyable_message_refused(world):
    await world.owner.send("/broadcast")
    invoice = Invoice(
        title="t", description="d", start_parameter="s", currency="USD", total_amount=1
    )
    await world.owner.send(invoice=invoice)
    assert world.telegram.last_text(OWNER_ID) == texts.BROADCAST_NOT_COPYABLE


async def test_blocked_users_are_counted_and_skipped_next_time(world):
    await add_users(world, 1, 2)

    def copy(method):
        if method.chat_id == 1:
            raise TelegramForbiddenError(method, "bot was blocked by the user")
        return MessageId(message_id=1)

    world.telegram.set(CopyMessage, copy)
    await start_broadcast(world)
    assert "Couldn't receive it: 1" in world.telegram.last_text(OWNER_ID)
    assert 1 not in await world.app.users.reachable_after(0)
    assert 2 in await world.app.users.reachable_after(0)


async def test_deleted_accounts_are_marked(world):
    await add_users(world, 1)

    def copy(method):
        if method.chat_id == 1:
            raise TelegramBadRequest(method, "chat not found")
        return MessageId(message_id=1)

    world.telegram.set(CopyMessage, copy)
    await start_broadcast(world)
    assert 1 not in await world.app.users.reachable_after(0)


async def test_other_problem_with_one_person_keeps_them(world):
    await add_users(world, 1)

    def copy(method):
        if method.chat_id == 1:
            raise TelegramBadRequest(method, "something odd")
        return MessageId(message_id=1)

    world.telegram.set(CopyMessage, copy)
    await start_broadcast(world)
    assert 1 in await world.app.users.reachable_after(0)


async def test_banned_users_dont_receive_it(world):
    await add_users(world, 1, 2)
    await world.app.users.set_banned(1, True)
    await start_broadcast(world)
    assert 1 not in targets(world) and 2 in targets(world)


async def test_slow_down_requests_are_obeyed(world, monkeypatch):
    await add_users(world, 1)
    slept = []
    real_sleep = service.asyncio.sleep

    async def sleep(seconds):
        slept.append(seconds)
        await real_sleep(0)

    monkeypatch.setattr(service.asyncio, "sleep", sleep)
    limited = []

    def copy(method):
        if method.chat_id == 1 and not limited:
            limited.append(True)
            raise TelegramRetryAfter(method, "slow", 120)
        return MessageId(message_id=1)

    world.telegram.set(CopyMessage, copy)
    await start_broadcast(world)
    assert 121 in slept
    assert 1 in targets(world)


async def test_deleted_source_stops_with_explanation(world):
    await add_users(world, 1, 2)
    calls = []

    def copy(method):
        calls.append(method)
        if len(calls) == 1:
            return MessageId(message_id=1)  # The preview worked.
        raise TelegramBadRequest(method, "message to copy not found")

    world.telegram.set(CopyMessage, copy)
    await start_broadcast(world)
    assert world.telegram.last_text(OWNER_ID) == texts.BROADCAST_SOURCE_GONE.format(sent=0)
    assert await world.app.jobs.running() == []


async def test_second_broadcast_while_one_runs_is_refused(world):
    await world.app.jobs.create(
        service.KIND, OWNER_ID, {"chat_id": 1, "message_id": 1, "progress_id": 1}
    )
    await world.owner.tap("bc:go:5")
    assert world.telegram.of(AnswerCallbackQuery)[-1].text == texts.BROADCAST_BUSY


async def test_restart_resumes_after_last_person(world):
    await add_users(world, 1, 2, 3)
    job_id = await world.app.jobs.create(
        service.KIND, OWNER_ID, {"chat_id": OWNER_ID, "message_id": 1, "progress_id": 1}
    )
    await world.app.jobs.save_progress(job_id, 2, {"sent": 2, "failed": 0})
    await world.app.runner.resume_all()
    await world.app.runner.wait()
    assert targets(world) == [3]
    assert world.telegram.last_text(OWNER_ID) == texts.BROADCAST_DONE.format(sent=3, failed=0)


async def test_stop_button(world, monkeypatch):
    monkeypatch.setattr(service, "CANCEL_CHECK_EVERY", 1)
    await add_users(world, 1, 2)
    job_id = await world.app.jobs.create(
        service.KIND, OWNER_ID, {"chat_id": OWNER_ID, "message_id": 1, "progress_id": 1}
    )
    await world.owner.tap(f"bc:stop:{job_id}")
    job = await world.app.jobs.get(job_id)
    assert job["status"] == "cancelled"
    await world.app.runner.resume_all()
    await world.app.runner.wait()
    assert targets(world) == []


async def test_stop_mid_run_reports(world, monkeypatch):
    monkeypatch.setattr(service, "CANCEL_CHECK_EVERY", 1)
    await add_users(world, 1, 2)
    job_id = await world.app.jobs.create(
        service.KIND, OWNER_ID, {"chat_id": OWNER_ID, "message_id": 1, "progress_id": 1}
    )

    def copy(method):
        return MessageId(message_id=1)

    world.telegram.set(CopyMessage, copy)
    real = world.app.jobs.is_cancelled
    answers = iter([True])

    async def cancelled(job):
        return next(answers, await real(job))

    monkeypatch.setattr(world.app.jobs, "is_cancelled", cancelled)
    await world.app.runner.resume_all()
    await world.app.runner.wait()
    assert texts.BROADCAST_STOPPED.format(sent=0, failed=0) == world.telegram.last_text(OWNER_ID)
    assert job_id


async def test_user_cannot_broadcast(world):
    await world.person(5).send("/broadcast")
    assert world.telegram.last_text(5) == texts.UNKNOWN_MESSAGE
    await world.person(5).tap("bc:go:1")
    assert await world.app.jobs.running() == []
