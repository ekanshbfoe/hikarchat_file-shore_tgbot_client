"""The logs group: what the client sees, and approving or banning let-through users."""

import shutil

import pytest
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramMigrateToChat,
)
from aiogram.methods import (
    AnswerCallbackQuery,
    CopyMessage,
    CopyMessages,
    EditMessageCaption,
    EditMessageReplyMarkup,
    GetChatMember,
    SendMessage,
)
from aiogram.types import Chat, PhotoSize

from bot import texts
from bot.db.links import Item
from bot.db.targets import YOUTUBE
from bot.services import activity_log
from tests import screenshots
from tests.fake_telegram import button_data
from tests.helpers import OWNER_ID

pytestmark = pytest.mark.skipif(shutil.which("tesseract") is None, reason="needs tesseract")

LOG = -100900
USER = 5
PHOTO = [PhotoSize(file_id="p", file_unique_id="u", width=1080, height=2200)]
GROUP = Chat(id=LOG, type="supergroup")


@pytest.fixture
def logged(world):
    world.app.config.log_chat_id = LOG
    return world


async def lines(world):
    await world.app.log.drain()
    return [c.text for c in world.telegram.of(SendMessage) if c.chat_id == LOG]


async def join(world):
    target, _ = await world.app.targets.add(YOUTUBE, "@cool", "Cool Edits", "https://y.t/@cool")
    code = await world.app.links.create(
        "genlink", OWNER_ID, [Item(channel_id=-100500, message_id=1)]
    )
    return target, code


async def fail_three_times(world, person, code):
    await person.send(f"/start {code}")
    world.telegram.file_bytes = screenshots.unrelated()
    for _ in range(3):
        await person.send(photo=PHOTO)
    await world.app.log.drain()


def delivered(world, user=USER):
    return [c for c in world.telegram.of(CopyMessages) if c.chat_id == user]


def review_message(world):
    return next(c for c in world.telegram.of(CopyMessage) if c.chat_id == LOG)


async def tap_review(world, person, action, user_id=USER, target_id=1, photo=True):
    fields = {"photo": PHOTO, "caption": "Please review"} if photo else {"text": "Please review"}
    message = person.message(chat=GROUP, **fields)
    await person.tap(f"rv:{action}:{user_id}:{target_id}", message=message)


# --- Reviewing ---


async def test_third_failure_lets_them_through_and_shows_staff_the_screenshot(logged):
    _, code = await join(logged)
    person = logged.person(USER, "tester")
    await fail_three_times(logged, person, code)
    assert delivered(logged)
    sent = review_message(logged)
    assert sent.from_chat_id == USER
    assert "Cool Edits" in sent.caption and "3 tries" in sent.caption
    assert str(USER) in sent.caption
    assert button_data(sent.reply_markup) == [f"rv:ok:{USER}:1", f"rv:no:{USER}:1"]


async def test_no_review_for_people_who_pass_normally(logged):
    _, code = await join(logged)
    person = logged.person(USER)
    await person.send(f"/start {code}")
    logged.telegram.file_bytes = screenshots.youtube(name="Cool Edits", handle="@cool")
    await person.send(photo=PHOTO)
    await logged.app.log.drain()
    assert delivered(logged)
    assert not [c for c in logged.telegram.of(CopyMessage) if c.chat_id == LOG]


async def test_not_approve_bans_them(logged):
    _, code = await join(logged)
    person = logged.person(USER)
    await fail_three_times(logged, person, code)
    await tap_review(logged, logged.owner, "no")
    assert await logged.app.users.is_banned(USER)
    edited = logged.telegram.of(EditMessageCaption)[-1]
    assert "banned by" in edited.caption and edited.reply_markup is None
    await person.send(f"/start {code}")
    assert logged.telegram.last_text(USER) == texts.BANNED


async def test_approve_leaves_them_alone_and_they_stay_verified(logged):
    _, code = await join(logged)
    person = logged.person(USER)
    await fail_three_times(logged, person, code)
    await tap_review(logged, logged.owner, "ok")
    assert not await logged.app.users.is_banned(USER)
    assert "Approved by" in logged.telegram.of(EditMessageCaption)[-1].caption
    logged.telegram.clear()
    await person.send(f"/start {code}")
    assert delivered(logged)


async def test_moderator_can_decide(logged):
    await logged.app.roles.add_by_username("mod", OWNER_ID)
    _, code = await join(logged)
    await fail_three_times(logged, logged.person(USER), code)
    await tap_review(logged, logged.person(8, "mod"), "no")
    assert await logged.app.users.is_banned(USER)


async def test_ordinary_group_member_cannot_decide(logged):
    _, code = await join(logged)
    await fail_three_times(logged, logged.person(USER), code)
    await tap_review(logged, logged.person(6), "no")
    assert not await logged.app.users.is_banned(USER)
    assert logged.telegram.of(AnswerCallbackQuery)[-1].text == texts.REVIEW_STAFF_ONLY
    await tap_review(logged, logged.owner, "ok")  # The decision is still open.
    assert "Approved by" in logged.telegram.of(EditMessageCaption)[-1].caption


async def test_first_decision_wins(logged):
    _, code = await join(logged)
    await fail_three_times(logged, logged.person(USER), code)
    await tap_review(logged, logged.owner, "ok")
    await tap_review(logged, logged.owner, "no")
    assert not await logged.app.users.is_banned(USER)
    assert logged.telegram.of(AnswerCallbackQuery)[-1].text == texts.REVIEW_ALREADY_DECIDED
    assert logged.telegram.of(EditMessageReplyMarkup)


async def test_double_tap_on_not_approve_is_harmless(logged):
    _, code = await join(logged)
    await fail_three_times(logged, logged.person(USER), code)
    await tap_review(logged, logged.owner, "no")
    await tap_review(logged, logged.owner, "no")
    assert await logged.app.users.is_banned(USER)
    assert logged.telegram.of(AnswerCallbackQuery)[-1].text == texts.REVIEW_ALREADY_DECIDED


async def test_unbanned_person_starts_again(logged):
    _, code = await join(logged)
    person = logged.person(USER)
    await fail_three_times(logged, person, code)
    await tap_review(logged, logged.owner, "no")
    await logged.owner.send(f"/unban {USER}")
    logged.telegram.clear()
    await person.send(f"/start {code}")
    assert not delivered(logged)
    assert "Almost there" in logged.telegram.last_text(USER)
    # Their attempts were cleared too, so one bad picture doesn't let them through.
    logged.telegram.file_bytes = screenshots.unrelated()
    await person.send(photo=PHOTO)
    assert not delivered(logged)


async def test_rejected_person_waiting_on_a_link_gets_nothing_after_unban(logged):
    _, code = await join(logged)
    person = logged.person(USER)
    await fail_three_times(logged, person, code)
    await logged.app.users.set_pending(USER, code)
    await tap_review(logged, logged.owner, "no")
    assert await logged.app.users.get_pending(USER) is None


async def test_someone_who_became_a_moderator_cant_be_banned_this_way(logged):
    _, code = await join(logged)
    person = logged.person(USER, "later_mod")
    await fail_three_times(logged, person, code)
    await logged.app.roles.add_by_username("later_mod", OWNER_ID)
    await tap_review(logged, logged.owner, "no")
    assert not await logged.app.users.is_banned(USER)
    assert logged.telegram.of(AnswerCallbackQuery)[-1].text == texts.REVIEW_IS_STAFF


async def test_deleted_screenshot_still_gets_a_review(logged):
    _, code = await join(logged)
    real = logged.telegram._default

    def copy(method):
        if method.chat_id == LOG:
            raise TelegramBadRequest(method, "message to copy not found")
        return real(method)

    logged.telegram.set(CopyMessage, copy)
    await fail_three_times(logged, logged.person(USER), code)
    await logged.app.log.drain()
    review = [c for c in logged.telegram.of(SendMessage) if c.chat_id == LOG and c.reply_markup]
    assert texts.REVIEW_NO_PICTURE in review[0].text
    assert button_data(review[0].reply_markup)


async def test_review_of_a_text_message_edits_text(logged):
    _, code = await join(logged)
    await fail_three_times(logged, logged.person(USER), code)
    await tap_review(logged, logged.owner, "ok", photo=False)
    assert "Approved by" in logged.telegram.of_edit_text(-1)


async def test_without_a_logs_group_they_are_still_let_through(world):
    _, code = await join(world)
    await fail_three_times(world, world.person(USER), code)
    assert delivered(world)
    assert not [c for c in world.telegram.of(CopyMessage) if c.chat_id == LOG]


async def test_keep_asking_setting_means_no_review(logged):
    logged.app.config.screenshot_max_attempts = 0
    _, code = await join(logged)
    await fail_three_times(logged, logged.person(USER), code)
    assert not delivered(logged)
    assert not [c for c in logged.telegram.of(CopyMessage) if c.chat_id == LOG]


async def test_junk_review_buttons_are_ignored(logged):
    await logged.owner.tap("rv:no:notanumber:1")
    assert logged.telegram.of(AnswerCallbackQuery)[-1].text == texts.REVIEW_STAFF_ONLY


# --- What gets logged ---


async def test_new_user_logged_once(logged):
    person = logged.person(USER, "first")
    await person.send("/start")
    await person.send("/start")
    await logged.app.store.cache.delete_prefix("seen:")
    await person.send("/start")
    found = [t for t in await lines(logged) if "New user" in t and str(USER) in t]
    assert len(found) == 1


async def test_names_are_escaped(logged):
    person = logged.person(USER)
    person.user = person.user.model_copy(update={"first_name": "<b>x</b>"})
    await person.send("/start")
    assert any("&lt;b&gt;" in t for t in await lines(logged))


async def test_staff_actions_are_logged(logged):
    owner = logged.owner
    await owner.send("/genlink")
    await owner.send("file")
    await owner.tap("collect:done")
    await owner.send("/ban 77")
    await owner.send("/unban 77")
    await owner.tap("set:protect")
    await owner.tap("set:caption:edit")
    await owner.send("new caption")
    await owner.tap("set:mods:add")
    await owner.send("@somemod")
    joined = "\n".join(await lines(logged))
    for expected in (
        "created a link",
        "banned <code>77</code>",
        "unbanned <code>77</code>",
        "Protect Content on",
        "custom caption",
        "added moderator @somemod",
    ):
        assert expected in joined


async def test_force_subscribe_changes_are_logged(logged):
    owner = logged.owner
    await owner.tap("fs:add:youtube")
    await owner.send("@cool")
    await owner.send("Cool Edits")
    target = (await logged.app.targets.list_active())[0]
    await owner.tap(f"fs:rename:{target['id']}")
    await owner.send("Better")
    await owner.tap(f"fs:askyes:{target['id']}")
    await owner.tap(f"fs:replace:{target['id']}")
    await owner.send("@other")
    await owner.send("Other")
    other = (await logged.app.targets.list_active())[0]
    await owner.tap(f"fs:rm:{other['id']}")
    await owner.tap("fs:add:youtube")
    await owner.send("@other")
    await owner.send("Other")
    joined = "\n".join(await lines(logged))
    for expected in (
        "added to force subscribe: <b>Cool Edits</b> (YouTube)",
        "renamed",
        "confirm <b>Better</b> again",
        "changed <b>Better</b> to <b>Other</b>",
        "removed from force subscribe: <b>Other</b>",
        "brought back to force subscribe: <b>Other</b>",
    ):
        assert expected in joined


async def test_duplicate_add_isnt_logged_as_a_change(logged):
    await logged.app.targets.add(YOUTUBE, "@cool", "Cool", "u")
    await logged.owner.tap("fs:add:youtube")
    await logged.owner.send("@cool")
    await logged.owner.send("Cool")
    assert not [t for t in await lines(logged) if "force subscribe" in t]


async def test_broadcast_is_logged_start_and_finish(logged):
    await logged.owner.send("/broadcast")
    await logged.owner.send("news")
    await logged.owner.tap(button_data(logged.telegram.last_markup(OWNER_ID))[0])
    await logged.app.runner.wait()
    joined = "\n".join(await lines(logged))
    assert "started a broadcast" in joined and "Broadcast finished" in joined


async def test_shortener_key_never_reaches_the_group(logged, monkeypatch):
    from bot.handlers import settings as handler

    async def fake(url, site, key):
        return "https://s.io/ok"

    monkeypatch.setattr(handler, "shorten", fake)
    await logged.owner.tap("set:short:edit")
    await logged.owner.send("short.example.com")
    await logged.owner.send("SECRETKEY")
    joined = "\n".join(await lines(logged))
    assert "short.example.com" in joined and "SECRETKEY" not in joined


# --- It must never get in anyone's way ---


async def test_broken_logs_group_doesnt_stop_delivery_and_tells_owner_once(logged):
    real = logged.telegram._default

    def send(method):
        if method.chat_id == LOG:
            raise TelegramForbiddenError(method, "bot was kicked")
        return real(method)

    logged.telegram.set(SendMessage, send)
    _, code = await join(logged)
    await logged.person(USER).send(f"/start {code}")
    await logged.person(6).send(f"/start {code}")
    await logged.app.log.drain()
    assert logged.telegram.last_text(USER)
    assert logged.telegram.texts_to(OWNER_ID).count(texts.LOG_CHAT_NOTICE) == 1


async def test_upgraded_group_is_followed_to_its_new_address(logged):
    real = logged.telegram._default

    def send(method):
        if method.chat_id == LOG:
            raise TelegramMigrateToChat(method, "upgraded", -100901)
        return real(method)

    logged.telegram.set(SendMessage, send)
    logged.app.log.post("hello")
    await logged.app.log.drain()
    assert logged.telegram.texts_to(-100901) == ["hello"]
    assert await logged.app.log.chat_id() == -100901


async def test_reviews_jump_the_queue(logged):
    log = logged.app.log
    await log.stop()
    log.post("one")
    log.post("two")

    class Fake:
        message_id = 1
        chat = Chat(id=USER, type="private")
        from_user = logged.person(USER).user

    log.review(Fake, {"id": 1, "display_name": "N", "platform": "youtube"}, 3)
    log.start()
    await log.drain()
    order = [type(c).__name__ for c in logged.telegram.calls if getattr(c, "chat_id", 0) == LOG]
    assert order[0] == "CopyMessage"


async def test_full_queue_drops_lines_but_never_reviews(logged, monkeypatch):
    log = logged.app.log
    await log.stop()
    monkeypatch.setattr(activity_log, "MAX_QUEUED", 1)
    log.post("kept")
    log.post("dropped")

    class Fake:
        message_id = 1
        chat = Chat(id=USER, type="private")
        from_user = logged.person(USER).user

    log.review(Fake, {"id": 1, "display_name": "N", "platform": "youtube"}, 3)
    assert log._queue.qsize() == 2
    log.start()
    await log.drain()


async def test_access_check_tells_owner_when_missing(logged):
    logged.telegram.set_member({LOG: "member"})
    logged.telegram.set(GetChatMember, TelegramBadRequest(GetChatMember, "chat not found"))
    assert not await logged.app.log.check_access()
    assert logged.telegram.texts_to(OWNER_ID) == [texts.LOG_CHAT_NOTICE]


async def test_access_check_is_quiet_without_a_group(world):
    assert await world.app.log.check_access()
    assert world.telegram.texts_to(OWNER_ID) == []
