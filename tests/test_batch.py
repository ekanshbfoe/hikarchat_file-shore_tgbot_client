from datetime import UTC, datetime

from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.methods import CopyMessages, GetChat, GetChatMember
from aiogram.types import (
    Chat,
    ChatMemberMember,
    MessageId,
    MessageOriginChannel,
    User,
)

from bot import texts
from bot.services import batch as batch_service
from tests.fake_telegram import BOT_ID, bot_admin
from tests.helpers import OWNER_ID

CHANNEL = -100123


def admin():
    return bot_admin()


def origin(post_id, channel=CHANNEL):
    return MessageOriginChannel(
        date=datetime(2026, 1, 1, tzinfo=UTC),
        chat=Chat(id=channel, type="channel"),
        message_id=post_id,
    )


def allow_channel(world):
    world.telegram.set(GetChatMember, lambda m: admin())


async def run_batch(world, first=1, last=3):
    allow_channel(world)
    await world.owner.send("/batch")
    await world.owner.send(forward_origin=origin(first), text="p")
    await world.owner.send(forward_origin=origin(last), text="p")
    await world.app.runner.wait()


async def test_forwarded_posts_make_a_link(world):
    await run_batch(world)
    final = world.telegram.last_text(OWNER_ID)
    assert "3 saved" in final
    code = final.rsplit("start=", 1)[1]
    link = await world.app.links.get(code)
    assert len(link["items"]) == 3 and link["kind"] == "batch"
    copied = world.telegram.of(CopyMessages)[0]
    assert copied.from_chat_id == CHANNEL and copied.message_ids == [1, 2, 3]
    assert copied.chat_id == world.app.config.backup_channel_id


async def test_reverse_order_is_swapped(world):
    await run_batch(world, first=5, last=2)
    assert world.telegram.of(CopyMessages)[0].message_ids == [2, 3, 4, 5]


async def test_single_post_range(world):
    await run_batch(world, first=7, last=7)
    assert world.telegram.of(CopyMessages)[0].message_ids == [7]


async def test_links_are_accepted_as_well_as_forwards(world):
    allow_channel(world)
    await world.owner.send("/batch")
    await world.owner.send("https://t.me/c/123/10")
    await world.owner.send("t.me/c/123/12")
    await world.app.runner.wait()
    copied = world.telegram.of(CopyMessages)[0]
    assert copied.from_chat_id == CHANNEL and copied.message_ids == [10, 11, 12]


async def test_public_channel_link(world):
    allow_channel(world)
    await world.owner.send("/batch")
    await world.owner.send("https://t.me/somechannel/5")
    await world.owner.send("https://t.me/somechannel/6?single")
    await world.app.runner.wait()
    assert world.telegram.of(CopyMessages)[0].message_ids == [5, 6]


async def test_large_range_is_split_into_hundreds(world):
    await run_batch(world, first=1, last=250)
    assert [len(c.message_ids) for c in world.telegram.of(CopyMessages)] == [100, 100, 50]
    assert "250 saved" in world.telegram.last_text(OWNER_ID)


async def test_gaps_are_skipped(world):
    allow_channel(world)
    world.telegram.set(CopyMessages, lambda m: [MessageId(message_id=1)])
    await run_batch(world, first=1, last=3)
    assert "1 saved" in world.telegram.last_text(OWNER_ID)


async def test_empty_range_removes_the_link(world):
    world.telegram.set(CopyMessages, lambda m: [])
    await run_batch(world)
    assert world.telegram.last_text(OWNER_ID) == texts.BATCH_EMPTY


async def test_not_a_post_is_explained(world):
    await world.owner.send("/batch")
    await world.owner.send("hello")
    assert world.telegram.last_text(OWNER_ID) == texts.BATCH_NOT_A_POST


async def test_different_channels_refused(world):
    allow_channel(world)
    await world.owner.send("/batch")
    await world.owner.send(forward_origin=origin(1), text="p")
    await world.owner.send(forward_origin=origin(2, channel=-100999), text="p")
    assert world.telegram.last_text(OWNER_ID) == texts.BATCH_DIFFERENT_CHANNEL


async def test_too_many_is_explained(world):
    allow_channel(world)
    await world.owner.send("/batch")
    await world.owner.send(forward_origin=origin(1), text="p")
    await world.owner.send(forward_origin=origin(batch_service.MAX_POSTS + 5), text="p")
    assert "the most I can store" in world.telegram.last_text(OWNER_ID)
    assert not world.telegram.of(CopyMessages)


async def test_bot_not_admin_gets_instruction(world):
    world.telegram.set(
        GetChatMember,
        lambda m: ChatMemberMember(user=User(id=BOT_ID, is_bot=True, first_name="b")),
    )
    await world.owner.send("/batch")
    await world.owner.send(forward_origin=origin(1), text="p")
    assert world.telegram.last_text(OWNER_ID) == texts.BATCH_NOT_ADMIN


async def test_unreachable_channel_gets_instruction(world):
    world.telegram.set(GetChat, TelegramBadRequest(GetChat, "chat not found"))
    await world.owner.send("/batch")
    await world.owner.send(forward_origin=origin(1), text="p")
    assert world.telegram.last_text(OWNER_ID) == texts.BATCH_NOT_ADMIN


async def test_protected_channel_is_explained(world):
    allow_channel(world)
    real = world.telegram._default

    def protected(method):
        chat = real(method)
        return chat.model_copy(update={"has_protected_content": True})

    world.telegram.set(GetChat, protected)
    await world.owner.send("/batch")
    await world.owner.send(forward_origin=origin(1), text="p")
    assert world.telegram.last_text(OWNER_ID) == texts.BATCH_PROTECTED


async def test_losing_access_mid_way_stops_cleanly(world):
    world.telegram.set(CopyMessages, TelegramForbiddenError(CopyMessages, "kicked"))
    await run_batch(world)
    assert world.telegram.last_text(OWNER_ID) == texts.BATCH_FAILED
    assert await world.app.jobs.running() == []


async def test_ordinary_user_cannot_batch(world):
    await world.person(5).send("/batch")
    assert world.telegram.last_text(5) == texts.UNKNOWN_MESSAGE


async def test_restart_resumes_where_it_left_off(world):
    allow_channel(world)
    code = await world.app.links.create("batch", OWNER_ID, [])
    job_id = await world.app.jobs.create(
        batch_service.KIND,
        OWNER_ID,
        {
            "source": CHANNEL,
            "first": 1,
            "last": 250,
            "code": code,
            "chat_id": OWNER_ID,
            "progress_id": 1,
        },
    )
    await world.app.jobs.save_progress(job_id, 100, {"stored": 100})
    await world.app.runner.resume_all()
    await world.app.runner.wait()
    assert world.telegram.of(CopyMessages)[0].message_ids[0] == 101
    assert "250 saved" in world.telegram.last_text(OWNER_ID)
    assert (await world.app.jobs.get(job_id))["status"] == "done"


async def test_database_outage_mid_job_is_retried(world, monkeypatch):
    from bot.services import runner as runner_module

    monkeypatch.setattr(runner_module, "RETRY_SECONDS", 0)
    real = world.app.jobs.save_progress
    failures = [OSError("database asleep")]

    async def flaky(*args):
        if failures:
            raise failures.pop()
        await real(*args)

    monkeypatch.setattr(world.app.jobs, "save_progress", flaky)
    await run_batch(world)
    assert "saved" in world.telegram.last_text(OWNER_ID)


async def test_long_slowdown_from_telegram_doesnt_end_the_job(world, monkeypatch):
    from aiogram.exceptions import TelegramRetryAfter

    from bot.services import runner as runner_module

    waits = []
    real_sleep = runner_module.asyncio.sleep

    async def sleep(seconds):
        waits.append(seconds)
        await real_sleep(0)

    monkeypatch.setattr(runner_module.asyncio, "sleep", sleep)
    calls = []

    def copy(method):
        calls.append(method)
        if len(calls) == 1:
            raise TelegramRetryAfter(method, "slow", 300)
        return [MessageId(message_id=1)]

    world.telegram.set(CopyMessages, copy)
    await run_batch(world, first=1, last=1)
    assert 301 in waits
    assert "1 saved" in world.telegram.last_text(OWNER_ID)


async def test_unexpected_job_failure_tells_the_person_calmly(world, monkeypatch):
    async def explode(*args):
        raise RuntimeError("bug with secret detail")

    monkeypatch.setattr(world.app.jobs, "save_progress", explode)
    await run_batch(world)
    assert world.telegram.last_text(OWNER_ID) == texts.SOMETHING_WRONG
    assert await world.app.jobs.running() == []
