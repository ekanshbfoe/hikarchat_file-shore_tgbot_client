"""The whole force subscribe journey, through the real dispatcher and real OCR."""

import shutil

import pytest
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import AnswerCallbackQuery, CopyMessages, GetChatMember, GetFile
from aiogram.types import (
    Chat,
    ChatJoinRequest,
    ChatShared,
    Document,
    PhotoSize,
    Sticker,
)

from bot import texts
from bot.db.links import Item
from bot.db.targets import TELEGRAM, TIKTOK, YOUTUBE
from tests import screenshots
from tests.fake_telegram import button_data, button_urls
from tests.helpers import OWNER_ID

pytestmark = pytest.mark.skipif(shutil.which("tesseract") is None, reason="needs tesseract")

USER = 5
CHANNEL = -100111
PHOTO = [PhotoSize(file_id="p", file_unique_id="u", width=1080, height=2200)]


@pytest.fixture
async def code(world):
    return await world.app.links.create(
        "genlink", OWNER_ID, [Item(channel_id=-100500, message_id=1)]
    )


async def add_youtube(world, name="Cool Edits", identity="@cooledits"):
    target, _ = await world.app.targets.add(
        YOUTUBE, identity, name, f"https://www.youtube.com/{identity}"
    )
    return target


async def add_tiktok(world, name="Cool Edits", identity="@cooledits"):
    target, _ = await world.app.targets.add(
        TIKTOK, identity, name, f"https://www.tiktok.com/{identity}"
    )
    return target


async def add_channel(world, chat_id=CHANNEL, name="Updates"):
    target, _ = await world.app.targets.add(
        TELEGRAM, str(chat_id), name, "https://t.me/+abc", chat_id=chat_id
    )
    return target


def delivered(world, user=USER):
    return [c for c in world.telegram.of(CopyMessages) if c.chat_id == user]


async def send_screenshot(world, person, image):
    world.telegram.file_bytes = image
    await person.send(photo=PHOTO)


# --- No force subscribe configured ---


async def test_nothing_configured_delivers_straight_away(world, code):
    await world.person(USER).send(f"/start {code}")
    assert delivered(world)


# --- YouTube ---


async def test_screenshot_passes_and_files_arrive_automatically(world, code):
    await add_youtube(world)
    person = world.person(USER)
    await person.send(f"/start {code}")
    assert not delivered(world)
    screen = world.telegram.last_text(USER)
    assert "Cool Edits" in screen and "0 of 1" in screen
    assert "https://www.youtube.com/@cooledits" in button_urls(world.telegram.last_markup(USER))

    await send_screenshot(world, person, screenshots.youtube())
    assert delivered(world)
    assert texts.SCREENSHOT_OK in world.telegram.texts_to(USER)


async def test_not_subscribed_gets_clear_message_then_retry_works(world, code):
    await add_youtube(world)
    person = world.person(USER)
    await person.send(f"/start {code}")
    await send_screenshot(world, person, screenshots.youtube(subscribed=False))
    assert not delivered(world)
    assert "Subscribed" in world.telegram.last_text(USER)
    await send_screenshot(world, person, screenshots.youtube())
    assert delivered(world)


async def test_never_asked_twice_for_the_same_channel(world, code):
    await add_youtube(world)
    person = world.person(USER)
    await person.send(f"/start {code}")
    await send_screenshot(world, person, screenshots.youtube())
    world.telegram.clear()
    await person.send(f"/start {code}")
    assert delivered(world)
    assert not any("Almost there" in t for t in world.telegram.texts_to(USER))


async def test_stays_verified_after_a_disk_wipe(world, code):
    await add_youtube(world)
    person = world.person(USER)
    await person.send(f"/start {code}")
    await send_screenshot(world, person, screenshots.youtube())
    await world.app.store.cache.delete_prefix("")
    world.telegram.clear()
    await person.send(f"/start {code}")
    assert delivered(world)


async def test_tiktok_journey(world, code):
    await add_tiktok(world)
    person = world.person(USER)
    await person.send(f"/start {code}")
    await send_screenshot(world, person, screenshots.tiktok(state="not"))
    assert "Follow" in world.telegram.last_text(USER)
    assert not delivered(world)
    await send_screenshot(world, person, screenshots.tiktok())
    assert delivered(world)


async def test_unreadable_three_times_still_gets_through(world, code):
    await add_youtube(world)
    person = world.person(USER)
    await person.send(f"/start {code}")
    for _ in range(2):
        await send_screenshot(world, person, screenshots.unrelated())
        assert not delivered(world)
    await send_screenshot(world, person, screenshots.unrelated())
    assert delivered(world)


async def test_retry_limit_zero_keeps_asking(world, code):
    world.app.config.screenshot_max_attempts = 0
    await add_youtube(world)
    person = world.person(USER)
    await person.send(f"/start {code}")
    for _ in range(5):
        await send_screenshot(world, person, screenshots.unrelated())
    assert not delivered(world)


async def test_image_sent_as_file_is_accepted(world, code):
    await add_youtube(world)
    person = world.person(USER)
    await person.send(f"/start {code}")
    world.telegram.file_bytes = screenshots.youtube()
    await person.send(
        document=Document(file_id="d", file_unique_id="u", mime_type="image/png", file_size=100)
    )
    assert delivered(world)


async def test_huge_file_is_refused_politely(world, code):
    await add_youtube(world)
    person = world.person(USER)
    await person.send(f"/start {code}")
    await person.send(
        document=Document(
            file_id="d", file_unique_id="u", mime_type="image/png", file_size=30 * 1024 * 1024
        )
    )
    assert world.telegram.last_text(USER) == texts.SCREENSHOT_TOO_BIG


async def test_other_media_gets_asked_for_a_picture(world, code):
    await add_youtube(world)
    person = world.person(USER)
    await person.send(f"/start {code}")
    await person.send(
        document=Document(file_id="d", file_unique_id="u", mime_type="application/zip")
    )
    assert world.telegram.last_text(USER) == texts.SCREENSHOT_WRONG_TYPE
    sticker = Sticker(
        file_id="s",
        file_unique_id="u",
        type="regular",
        width=1,
        height=1,
        is_animated=False,
        is_video=False,
    )
    await person.send(sticker=sticker)
    assert world.telegram.last_text(USER) == texts.SCREENSHOT_WRONG_TYPE


async def test_picture_when_nothing_is_waiting(world):
    await world.person(USER).send(photo=PHOTO)
    assert world.telegram.last_text(USER) == texts.SCREENSHOT_NOT_NEEDED


async def test_late_album_pictures_stay_quiet(world):
    await world.person(USER).send(photo=PHOTO, media_group_id="a")
    assert world.telegram.texts_to(USER) == []


async def test_text_while_waiting_shows_what_is_left(world, code):
    await add_youtube(world)
    person = world.person(USER)
    await person.send(f"/start {code}")
    await person.send("what do I do?")
    assert "Almost there" in world.telegram.last_text(USER)


async def test_download_failure_doesnt_block_the_person(world, code):
    await add_youtube(world)
    person = world.person(USER)
    await person.send(f"/start {code}")
    world.telegram.set(GetFile, TelegramBadRequest(GetFile, "file is too big"))
    await person.send(photo=PHOTO)
    assert delivered(world)


async def test_second_link_mid_flow_delivers_the_latest(world, code):
    other = await world.app.links.create(
        "genlink", OWNER_ID, [Item(channel_id=-100500, message_id=99)]
    )
    await add_youtube(world)
    person = world.person(USER)
    await person.send(f"/start {code}")
    await person.send(f"/start {other}")
    await send_screenshot(world, person, screenshots.youtube())
    assert [c.message_ids for c in delivered(world)] == [[99]]


async def test_link_deleted_while_waiting(world, code):
    await add_youtube(world)
    person = world.person(USER)
    await person.send(f"/start {code}")
    await world.app.links.delete(code)
    await send_screenshot(world, person, screenshots.youtube())
    assert world.telegram.last_text(USER) == texts.LINK_GONE


async def test_invalid_link_doesnt_start_the_flow(world):
    await add_youtube(world)
    await world.person(USER).send("/start nosuchcode")
    assert world.telegram.last_text(USER) == texts.LINK_GONE
    assert await world.app.users.get_pending(USER) is None


async def test_owner_and_moderators_skip_force_subscribe(world, code):
    await add_youtube(world)
    await world.app.roles.add_by_username("m", OWNER_ID)
    await world.owner.send(f"/start {code}")
    await world.person(8, "m").send(f"/start {code}")
    assert delivered(world, OWNER_ID) and delivered(world, 8)


async def test_names_with_html_are_safe(world, code):
    await add_youtube(world, name="<A&B>", identity="@ab")
    await world.person(USER).send(f"/start {code}")
    assert "&lt;A&amp;B&gt;" in world.telegram.last_text(USER)


# --- Several channels ---


async def test_screenshots_in_any_order_each_credited_correctly(world, code):
    await add_youtube(world, name="Alpha Clips", identity="@alpha")
    await add_youtube(world, name="Bravo Studio", identity="@bravo")
    person = world.person(USER)
    await person.send(f"/start {code}")
    assert "0 of 2" in world.telegram.last_text(USER)

    await send_screenshot(world, person, screenshots.youtube(name="Bravo Studio", handle="@bravo"))
    assert "1 of 2" in world.telegram.last_text(USER)
    assert "Alpha Clips" in world.telegram.last_text(USER)
    assert not delivered(world)

    await send_screenshot(world, person, screenshots.youtube(name="Alpha Clips", handle="@alpha"))
    assert delivered(world)


async def test_mixed_telegram_youtube_tiktok(world, code):
    await add_channel(world)
    await add_youtube(world, name="Alpha Clips", identity="@alpha")
    await add_tiktok(world, name="Bravo Studio", identity="@bravo")
    world.telegram.set_member({})
    person = world.person(USER)
    await person.send(f"/start {code}")
    assert "0 of 3" in world.telegram.last_text(USER)

    await send_screenshot(world, person, screenshots.youtube(name="Alpha Clips", handle="@alpha"))
    await send_screenshot(world, person, screenshots.tiktok(name="Bravo Studio", handle="@bravo"))
    assert not delivered(world)
    assert "Updates" in world.telegram.last_text(USER)

    await person.tap("gate:check")
    assert world.telegram.of(AnswerCallbackQuery)[-1].text == texts.GATE_NOT_YET
    world.telegram.set_member({CHANNEL: "member"})
    await person.tap("gate:check")
    assert delivered(world)


async def test_screenshot_when_only_telegram_is_left(world, code):
    await add_channel(world)
    world.telegram.set_member({})
    person = world.person(USER)
    await person.send(f"/start {code}")
    await person.send(photo=PHOTO)
    assert world.telegram.last_text(USER) == texts.SCREENSHOT_JOIN_FIRST


# --- Everything the owner can change ---


async def test_new_channel_asks_only_for_the_new_one(world, code):
    await add_youtube(world, name="Alpha Clips", identity="@alpha")
    person = world.person(USER)
    await person.send(f"/start {code}")
    await send_screenshot(world, person, screenshots.youtube(name="Alpha Clips", handle="@alpha"))
    world.telegram.clear()

    await add_youtube(world, name="Bravo Studio", identity="@bravo")
    await person.send(f"/start {code}")
    screen = world.telegram.last_text(USER)
    assert "Bravo Studio" in screen and "Alpha Clips" not in screen and "1 of 2" in screen


async def test_removed_channel_stops_being_asked(world, code):
    target = await add_youtube(world)
    await world.app.targets.remove(target["id"])
    await world.person(USER).send(f"/start {code}")
    assert delivered(world)


async def test_removed_mid_flow_delivers_on_next_step(world, code):
    target = await add_channel(world)
    world.telegram.set_member({})
    person = world.person(USER)
    await person.send(f"/start {code}")
    await world.app.targets.remove(target["id"])
    await person.tap("gate:check")
    assert delivered(world)


async def test_added_mid_flow_is_required_at_once(world, code):
    await add_youtube(world, name="Alpha Clips", identity="@alpha")
    person = world.person(USER)
    await person.send(f"/start {code}")
    await add_youtube(world, name="Bravo Studio", identity="@bravo")
    await send_screenshot(world, person, screenshots.youtube(name="Alpha Clips", handle="@alpha"))
    assert not delivered(world)
    assert "Bravo Studio" in world.telegram.last_text(USER)


async def test_channel_replaced_asks_everyone_again(world, code):
    target = await add_youtube(world, name="Alpha Clips", identity="@alpha")
    person = world.person(USER)
    await person.send(f"/start {code}")
    await send_screenshot(world, person, screenshots.youtube(name="Alpha Clips", handle="@alpha"))
    world.telegram.clear()

    await world.app.targets.replace(target["id"], "@bravo", "Bravo Studio", "https://x.io/@bravo")
    await person.send(f"/start {code}")
    assert not delivered(world)
    assert "Bravo Studio" in world.telegram.last_text(USER)


async def test_fixing_the_name_asks_nobody_again(world, code):
    target = await add_youtube(world)
    person = world.person(USER)
    await person.send(f"/start {code}")
    await send_screenshot(world, person, screenshots.youtube())
    world.telegram.clear()
    await world.app.targets.rename(target["id"], "Cool Edits Official")
    await person.send(f"/start {code}")
    assert delivered(world)


async def test_remove_then_readd_keeps_earlier_verification(world, code):
    target = await add_youtube(world)
    person = world.person(USER)
    await person.send(f"/start {code}")
    await send_screenshot(world, person, screenshots.youtube())
    world.telegram.clear()
    await world.app.targets.remove(target["id"])
    await add_youtube(world)
    await person.send(f"/start {code}")
    assert delivered(world)


async def test_ask_everyone_again(world, code):
    target = await add_youtube(world)
    person = world.person(USER)
    await person.send(f"/start {code}")
    await send_screenshot(world, person, screenshots.youtube())
    world.telegram.clear()
    await world.app.targets.ask_everyone_again(target["id"])
    await person.send(f"/start {code}")
    assert not delivered(world)
    await send_screenshot(world, person, screenshots.youtube())
    assert delivered(world)


async def test_attempts_reset_when_asked_again(world, code):
    target = await add_youtube(world)
    person = world.person(USER)
    await person.send(f"/start {code}")
    await send_screenshot(world, person, screenshots.unrelated())
    await send_screenshot(world, person, screenshots.unrelated())
    await world.app.targets.ask_everyone_again(target["id"])
    await send_screenshot(world, person, screenshots.unrelated())
    assert not delivered(world)


# --- Telegram membership ---


async def test_member_of_channel_is_never_bothered(world, code):
    await add_channel(world)
    world.telegram.set_member({CHANNEL: "member"})
    await world.person(USER).send(f"/start {code}")
    assert delivered(world)


async def test_admin_and_owner_of_channel_count_as_joined(world, code):
    await add_channel(world)
    world.telegram.set_member({CHANNEL: "admin"})
    await world.person(USER).send(f"/start {code}")
    assert delivered(world)


async def test_leaving_the_channel_is_noticed_after_the_short_memory(world, code):
    await add_channel(world)
    world.telegram.set_member({CHANNEL: "member"})
    person = world.person(USER)
    await person.send(f"/start {code}")
    assert delivered(world)
    world.telegram.clear()
    world.telegram.set_member({})
    await world.app.store.cache.delete_prefix("member:")
    await person.send(f"/start {code}")
    assert "Updates" in world.telegram.last_text(USER)


async def test_person_banned_from_channel_is_not_blocked_forever(world, code):
    await add_channel(world)
    world.telegram.set_member({CHANNEL: "kicked"})
    await world.person(USER).send(f"/start {code}")
    assert delivered(world)


async def test_bot_removed_from_channel_skips_it_and_tells_owner_once(world, code):
    await add_channel(world)
    world.telegram.set(GetChatMember, TelegramBadRequest(GetChatMember, "chat not found"))
    await world.person(USER).send(f"/start {code}")
    await world.person(6).send(f"/start {code}")
    assert delivered(world) and delivered(world, 6)
    assert len(world.telegram.texts_to(OWNER_ID)) == 1
    assert "Updates" in world.telegram.texts_to(OWNER_ID)[0]


async def test_join_request_counts_and_delivers(world, code):
    await add_channel(world)
    world.telegram.set_member({})
    person = world.person(USER)
    await person.send(f"/start {code}")
    request = ChatJoinRequest(
        chat=Chat(id=CHANNEL, type="channel"),
        from_user=person.user,
        user_chat_id=USER,
        date=0,
    )
    await person.feed(chat_join_request=request)
    assert delivered(world)


async def test_join_request_for_unrelated_chat_is_ignored(world):
    person = world.person(USER)
    request = ChatJoinRequest(
        chat=Chat(id=-1, type="channel"), from_user=person.user, user_chat_id=USER, date=0
    )
    await person.feed(chat_join_request=request)
    assert world.telegram.texts_to(USER) == []


async def test_group_upgrade_keeps_working(world, code):
    await add_channel(world, chat_id=-5, name="Group")
    await world.owner.send(chat=Chat(id=-5, type="group"), migrate_to_chat_id=-1005)
    target = await world.app.targets.find_by_chat(-1005)
    assert target is not None
    world.telegram.set_member({-1005: "member"})
    await world.person(USER).send(f"/start {code}")
    assert delivered(world)


async def test_check_button_with_nothing_waiting(world):
    await world.person(USER).tap("gate:check")
    assert world.telegram.of(AnswerCallbackQuery)[-1].text == texts.SCREENSHOT_NOT_NEEDED


async def test_banned_user_stays_out_mid_flow(world, code):
    await add_youtube(world)
    person = world.person(USER)
    await person.send(f"/start {code}")
    await world.app.users.set_banned(USER, True)
    await send_screenshot(world, person, screenshots.youtube())
    assert not delivered(world)
    assert world.telegram.last_text(USER) == texts.BANNED


# --- Owner's force subscribe settings ---


def owner_data(world):
    return button_data(world.telegram.last_markup(OWNER_ID))


async def test_owner_adds_youtube_and_tiktok(world):
    await world.owner.tap("fs:add:youtube")
    await world.owner.send("https://www.youtube.com/watch?v=abc")
    assert world.telegram.last_text(OWNER_ID) == texts.FS_LINK_VIDEO_YOUTUBE
    await world.owner.send("hello")
    assert world.telegram.last_text(OWNER_ID) == texts.FS_LINK_INVALID_YOUTUBE
    await world.owner.send("https://youtube.com/@CoolEdits?si=x")
    assert world.telegram.last_text(OWNER_ID) == texts.FS_NAME_PROMPT
    await world.owner.send("x" * 101)
    assert world.telegram.last_text(OWNER_ID) == texts.FS_NAME_INVALID
    await world.owner.send("Cool Edits")
    assert texts.FS_ADDED.format(name="Cool Edits") in world.telegram.texts_to(OWNER_ID)

    await world.owner.tap("fs:add:tiktok")
    await world.owner.send("hello")
    assert world.telegram.last_text(OWNER_ID) == texts.FS_LINK_INVALID_TIKTOK
    await world.owner.send("https://www.tiktok.com/@cooledits")
    await world.owner.send("Cool Edits")

    targets = await world.app.targets.list_active()
    assert [(t["platform"], t["identity"]) for t in targets] == [
        ("youtube", "@cooledits"),
        ("tiktok", "@cooledits"),
    ]


async def test_there_is_no_limit_on_how_many(world):
    for number in range(30):
        await add_youtube(world, name=f"Channel {number}", identity=f"@c{number}")
    await world.owner.tap("fs:home")
    assert len(await world.app.targets.list_active()) == 30
    assert sum(1 for d in owner_data(world) if d.startswith("fs:item:")) == 30


async def test_adding_same_channel_twice_says_so(world):
    await add_youtube(world)
    await world.owner.tap("fs:add:youtube")
    await world.owner.send("@cooledits")
    await world.owner.send("Other Name")
    assert texts.FS_ALREADY.format(name="Cool Edits") in world.telegram.texts_to(OWNER_ID)
    assert len(await world.app.targets.list_active()) == 1


async def test_owner_removes_through_buttons(world):
    target = await add_youtube(world)
    await world.owner.tap(f"fs:item:{target['id']}")
    assert f"fs:rm:{target['id']}" in owner_data(world)
    await world.owner.tap(f"fs:rm:{target['id']}")
    assert await world.app.targets.list_active() == []
    await world.owner.tap(f"fs:rm:{target['id']}")  # Double tap.
    assert world.telegram.of(AnswerCallbackQuery)[-1].text == texts.BUTTON_EXPIRED


async def test_owner_renames(world):
    target = await add_youtube(world)
    await world.owner.tap(f"fs:rename:{target['id']}")
    await world.owner.send("New Name")
    assert (await world.app.targets.get(target["id"]))["display_name"] == "New Name"
    assert texts.FS_RENAMED in world.telegram.texts_to(OWNER_ID)


async def test_owner_replaces(world):
    target = await add_youtube(world)
    await world.owner.tap(f"fs:replace:{target['id']}")
    await world.owner.send("@other")
    await world.owner.send("Other")
    assert [t["identity"] for t in await world.app.targets.list_active()] == ["@other"]
    assert texts.FS_REPLACED.format(name="Other") in world.telegram.texts_to(OWNER_ID)


async def test_replacing_with_the_same_channel_doesnt_ask_again(world):
    target = await add_youtube(world)
    await world.app.targets.mark_verified(USER, target, "screenshot")
    await world.owner.tap(f"fs:replace:{target['id']}")
    await world.owner.send("https://youtube.com/@COOLEDITS")
    await world.owner.send("Cool Edits")
    current = (await world.app.targets.list_active())[0]
    versions = await world.app.targets.verified_versions(USER)
    assert versions[str(current["id"])] == current["version"]


async def test_owner_asks_everyone_again_with_confirmation(world):
    target = await add_youtube(world)
    await world.owner.tap(f"fs:ask:{target['id']}")
    assert (await world.app.targets.get(target["id"]))["version"] == 1
    await world.owner.tap(f"fs:askyes:{target['id']}")
    assert (await world.app.targets.get(target["id"]))["version"] == 2


def share(request_id=1, chat_id=CHANNEL):
    return ChatShared(request_id=request_id, chat_id=chat_id)


async def test_owner_adds_telegram_channel_with_picker(world):
    world.telegram.set_member({CHANNEL: "admin"})
    await world.owner.tap("fs:add:channel")
    keyboard = world.telegram.last_markup(OWNER_ID).keyboard
    assert keyboard[0][0].request_chat.chat_is_channel is True
    await world.owner.send("typing instead")
    assert world.telegram.last_text(OWNER_ID) == texts.FS_PICK_FALLBACK
    await world.owner.send(chat_shared=share())
    target = (await world.app.targets.list_active())[0]
    assert target["chat_id"] == CHANNEL and target["url"] == "https://t.me/+newlink"


async def test_owner_adds_telegram_group(world):
    world.telegram.set_member({-1009: "admin"})
    await world.owner.tap("fs:add:group")
    assert world.telegram.last_markup(OWNER_ID).keyboard[0][0].request_chat.chat_is_channel is False
    await world.owner.send(chat_shared=share(request_id=2, chat_id=-1009))
    assert (await world.app.targets.list_active())[0]["chat_id"] == -1009


async def test_bot_not_admin_is_explained(world):
    world.telegram.set_member({CHANNEL: "member"})
    await world.owner.tap("fs:add:channel")
    await world.owner.send(chat_shared=share())
    assert "admin" in world.telegram.last_text(OWNER_ID)
    assert await world.app.targets.list_active() == []


async def test_unreachable_chat_is_explained(world):
    world.telegram.set(GetChatMember, TelegramBadRequest(GetChatMember, "chat not found"))
    await world.owner.tap("fs:add:channel")
    await world.owner.send(chat_shared=share())
    assert world.telegram.last_text(OWNER_ID) == texts.FS_CHAT_UNREACHABLE


async def test_moderators_and_users_cant_change_force_subscribe(world):
    target = await add_youtube(world)
    await world.app.roles.add_by_username("m", OWNER_ID)
    for person in (world.person(8, "m"), world.person(USER)):
        await person.tap(f"fs:rm:{target['id']}")
        await person.tap("fs:add:youtube")
    assert len(await world.app.targets.list_active()) == 1


async def test_banned_person_gets_nothing_from_a_join_request(world, code):
    await add_channel(world)
    world.telegram.set_member({})
    person = world.person(USER)
    await person.send(f"/start {code}")
    await world.app.users.set_banned(USER, True)
    request = ChatJoinRequest(
        chat=Chat(id=CHANNEL, type="channel"), from_user=person.user, user_chat_id=USER, date=0
    )
    await person.feed(chat_join_request=request)
    assert not delivered(world)
