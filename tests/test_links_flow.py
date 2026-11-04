from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.methods import CopyMessage, CopyMessages, EditMessageCaption, SendMessage
from aiogram.types import Document, InlineKeyboardMarkup, MessageId, PhotoSize

from bot import texts
from bot.db.links import Item
from bot.services import delivery
from bot.services.delivery import render_caption, split_runs
from tests.fake_telegram import button_data
from tests.helpers import OWNER_ID

BACKUP = -100500


def doc(name="a.xml", size=2048):
    return Document(file_id="f", file_unique_id="u", file_name=name, file_size=size)


def photo():
    return [PhotoSize(file_id="p", file_unique_id="u", width=1, height=1, file_size=10)]


async def make_link(world, *message_ids, **kw):
    items = [Item(channel_id=BACKUP, message_id=i, **kw) for i in message_ids]
    return await world.app.links.create("genlink", OWNER_ID, items)


# --- /start ---


async def test_start_welcomes_and_escapes_names(world):
    user = world.person(5)
    user.user = user.user.model_copy(update={"first_name": "<b>Al</b>"})
    await user.send("/start")
    assert "&lt;b&gt;Al&lt;/b&gt;" in world.telegram.last_text(5)


async def test_help_depends_on_role(world):
    user = world.person(5)
    await user.tap("home:help")
    assert world.telegram.of_edit_text(-1) == texts.HELP_USER
    await world.owner.tap("home:help")
    assert "/settings" in world.telegram.of_edit_text(-1)


# --- /genlink ---


async def test_genlink_full_flow(world):
    await world.owner.send("/genlink")
    await world.owner.send(document=doc())
    await world.owner.send("some text")
    world.telegram.clear()
    await world.owner.tap("collect:done")

    copied = world.telegram.of(CopyMessages)[0]
    assert copied.chat_id == BACKUP and copied.from_chat_id == OWNER_ID
    assert copied.message_ids == sorted(copied.message_ids)

    final = world.telegram.last_text(OWNER_ID)
    assert "https://t.me/store_bot?start=" in final
    code = final.rsplit("start=", 1)[1]
    link = await world.app.links.get(code)
    assert link["kind"] == "genlink"
    assert link["items"][0]["file_name"] == "a.xml" and link["items"][0]["has_media"]
    assert link["items"][1]["has_media"] is False
    assert all(item["channel_id"] == BACKUP for item in link["items"])


async def test_universal_link_works_like_genlink(world):
    await world.owner.send("/universal_link")
    await world.owner.send("text")
    await world.owner.tap("collect:done")
    code = world.telegram.last_text(OWNER_ID).rsplit("start=", 1)[1]
    assert (await world.app.links.get(code))["kind"] == "universal"


async def test_ordinary_user_cannot_create_links(world):
    user = world.person(5)
    await user.send("/genlink")
    assert world.telegram.last_text(5) == texts.UNKNOWN_MESSAGE
    await user.send("some text")
    await user.tap("collect:done")
    assert not world.telegram.of(CopyMessages)


async def test_moderator_can_create_links(world):
    await world.app.roles.add_by_username("mod", OWNER_ID)
    mod = world.person(8, "mod")
    await mod.send("/genlink")
    await mod.send("text")
    await mod.tap("collect:done")
    assert "start=" in world.telegram.last_text(8)


async def test_done_with_nothing_prompts(world):
    from aiogram.methods import AnswerCallbackQuery

    await world.owner.send("/genlink")
    await world.owner.tap("collect:done")
    assert world.telegram.of(AnswerCallbackQuery)[-1].text == texts.COLLECT_EMPTY
    await world.owner.send("still collecting")
    assert "1 ready" in world.telegram.last_text(OWNER_ID)


async def test_double_tapping_done_makes_one_link(world):
    await world.owner.send("/genlink")
    await world.owner.send("text")
    await world.owner.tap("collect:done")
    await world.owner.tap("collect:done")
    assert len(world.telegram.of(CopyMessages)) == 1


async def test_commands_mid_session_dont_get_stored(world):
    await world.owner.send("/genlink")
    await world.owner.send("/unknown_thing")
    assert world.telegram.last_text(OWNER_ID) == texts.COLLECT_COMMAND_HINT
    assert (await _session_sources(world)) == []


async def _session_sources(world):
    from aiogram.fsm.storage.base import StorageKey

    key = StorageKey(bot_id=world.app.bot.id, chat_id=OWNER_ID, user_id=OWNER_ID)
    return (await world.dispatcher.storage.get_data(key)).get("sources")


async def test_new_command_ends_session_cleanly(world):
    await world.owner.send("/genlink")
    await world.owner.send("text")
    await world.owner.send("/ban")  # ban runs, the session itself is untouched by it
    assert world.telegram.last_text(OWNER_ID) == texts.BAN_USAGE
    await world.owner.send("/genlink")
    assert await _session_sources(world) == []


async def test_cancel(world):
    await world.owner.send("/cancel")
    assert world.telegram.last_text(OWNER_ID) == texts.NOTHING_TO_CANCEL
    await world.owner.send("/genlink")
    await world.owner.send("/cancel")
    assert world.telegram.last_text(OWNER_ID) == texts.CANCELLED
    await world.owner.send("text")
    assert world.telegram.last_text(OWNER_ID) != texts.COLLECT_COUNT.format(count=1)


async def test_cancel_button(world):
    await world.owner.send("/genlink")
    await world.owner.tap("cancel")
    assert world.telegram.last_text(OWNER_ID) == texts.CANCELLED


async def test_uncopyable_message_is_refused_in_plain_words(world):
    from aiogram.types import Invoice

    await world.owner.send("/genlink")
    invoice = Invoice(
        title="t", description="d", start_parameter="s", currency="USD", total_amount=1
    )
    await world.owner.send(invoice=invoice)
    assert world.telegram.last_text(OWNER_ID) == texts.COLLECT_UNSUPPORTED
    assert await _session_sources(world) == []


async def test_album_answers_once_and_is_stored_together(world):
    await world.owner.send("/genlink")
    world.telegram.clear()
    for _ in range(3):
        await world.owner.send(photo=photo(), media_group_id="album1")
    assert len(world.telegram.of(SendMessage)) == 1
    await world.owner.tap("collect:done")
    assert len(world.telegram.of(CopyMessages)[0].message_ids) == 3


async def test_blocked_backup_channel_gets_plain_instruction_and_keeps_session(world):
    await world.owner.send("/genlink")
    await world.owner.send("text")
    world.telegram.set(CopyMessages, TelegramForbiddenError(CopyMessages, "forbidden"))
    await world.owner.tap("collect:done")
    assert world.telegram.last_text(OWNER_ID) == texts.STORAGE_BLOCKED
    assert len(await _session_sources(world)) == 1

    del world.telegram.overrides[CopyMessages]
    await world.owner.tap("collect:done")
    assert "start=" in world.telegram.last_text(OWNER_ID)


async def test_deleted_source_is_skipped_keeping_details_aligned(world):
    await world.owner.send("/genlink")
    await world.owner.send(document=doc("one.xml"))
    gone = await world.owner.send(document=doc("gone.xml"))
    await world.owner.send(document=doc("three.xml"))

    def copy_one(method):
        if method.message_id == gone.message_id:
            raise TelegramBadRequest(method, "message to copy not found")
        return MessageId(message_id=method.message_id + 5000)

    world.telegram.set(
        CopyMessages,
        lambda m: [MessageId(message_id=1), MessageId(message_id=2)],
    )
    world.telegram.set(CopyMessage, copy_one)
    await world.owner.tap("collect:done")
    code = world.telegram.last_text(OWNER_ID).rsplit("start=", 1)[1]
    names = [i["file_name"] for i in (await world.app.links.get(code))["items"]]
    assert names == ["one.xml", "three.xml"]


async def test_everything_deleted_is_explained(world):
    await world.owner.send("/genlink")
    await world.owner.send("text")
    world.telegram.set(CopyMessages, lambda m: [])
    world.telegram.set(CopyMessage, TelegramBadRequest(CopyMessage, "message to copy not found"))
    await world.owner.tap("collect:done")
    assert world.telegram.last_text(OWNER_ID) == texts.STORE_NOTHING_SAVED


# --- opening links ---


async def test_opening_link_delivers(world):
    code = await make_link(world, 10, 11)
    await world.person(5).send(f"/start {code}")
    sent = world.telegram.of(CopyMessages)[0]
    assert sent.chat_id == 5 and sent.from_chat_id == BACKUP and sent.message_ids == [10, 11]
    assert sent.protect_content is False


async def test_junk_and_unknown_codes_are_polite(world):
    for code in ("nosuchcode1", "../../etc", "a b c", "x" * 200):
        await world.person(5).send(f"/start {code}")
        assert world.telegram.last_text(5) == texts.LINK_GONE


async def test_some_files_deleted_delivers_the_rest(world):
    code = await make_link(world, 10, 11, 12)
    world.telegram.set(CopyMessages, lambda m: [MessageId(message_id=1)])
    await world.person(5).send(f"/start {code}")
    assert world.telegram.last_text(5) == texts.SOME_FILES_GONE


async def test_all_files_deleted(world):
    code = await make_link(world, 10)
    world.telegram.set(CopyMessages, lambda m: [])
    await world.person(5).send(f"/start {code}")
    assert world.telegram.last_text(5) == texts.FILES_GONE


async def test_user_who_blocked_bot_is_marked_and_not_reported(world):
    code = await make_link(world, 10)
    await world.person(5).send("hi")
    world.telegram.set(CopyMessages, TelegramForbiddenError(CopyMessages, "blocked"))
    await world.person(5).send(f"/start {code}")
    assert 5 not in await world.app.users.reachable_after(0)


async def test_protect_content_setting_is_applied(world):
    await world.app.settings.set("protect_content", True)
    code = await make_link(world, 10)
    await world.person(5).send(f"/start {code}")
    assert world.telegram.of(CopyMessages)[0].protect_content is True


async def test_custom_caption_and_button_on_single_file(world):
    await world.app.settings.set("custom_caption", "{filename} ({filesize}) {caption}")
    await world.app.settings.set("custom_button", {"text": "Join", "url": "https://t.me/x"})
    code = await world.app.links.create(
        "genlink",
        OWNER_ID,
        [
            Item(
                channel_id=BACKUP,
                message_id=10,
                file_name="a.xml",
                file_size=2048,
                caption="orig",
                has_media=True,
            )
        ],
    )
    await world.person(5).send(f"/start {code}")
    sent = world.telegram.of(CopyMessage)[0]
    assert sent.caption == "a.xml (2.0 KB) orig"
    assert sent.parse_mode is None
    assert isinstance(sent.reply_markup, InlineKeyboardMarkup)


async def test_text_message_gets_button_but_no_caption(world):
    await world.app.settings.set("custom_caption", "CAP")
    await world.app.settings.set("custom_button", {"text": "Join", "url": "https://t.me/x"})
    code = await make_link(world, 10)
    await world.person(5).send(f"/start {code}")
    sent = world.telegram.of(CopyMessage)[0]
    assert sent.caption is None and sent.reply_markup


async def test_album_with_custom_caption_stays_together(world):
    await world.app.settings.set("custom_caption", "CAP {filename}")
    await world.app.settings.set("custom_button", {"text": "Join", "url": "https://t.me/x"})
    code = await make_link(world, 10, 11, media_group_id="g", has_media=True, file_name="f")
    await world.person(5).send(f"/start {code}")
    assert world.telegram.of(CopyMessages)[0].message_ids == [10, 11]
    assert [c.caption for c in world.telegram.of(EditMessageCaption)] == ["CAP f", "CAP f"]
    tail = world.telegram.of(SendMessage)[-1]
    assert tail.text == texts.DELIVERY_TAIL_BUTTON and tail.reply_markup


async def test_caption_failure_on_album_doesnt_lose_the_files(world):
    await world.app.settings.set("custom_caption", "CAP")
    code = await make_link(world, 10, 11, media_group_id="g", has_media=True)
    world.telegram.set(EditMessageCaption, TelegramBadRequest(EditMessageCaption, "no"))
    await world.person(5).send(f"/start {code}")
    assert world.telegram.of(CopyMessages)
    assert texts.SOMETHING_WRONG not in world.telegram.texts_to(5)


async def test_bulk_batch_items_are_never_given_an_invented_caption(world):
    await world.app.settings.set("custom_caption", "CAP")
    code = await make_link(world, 10, 11, media_group_id=delivery.BULK_GROUP)
    await world.person(5).send(f"/start {code}")
    assert world.telegram.of(CopyMessages)
    assert not world.telegram.of(EditMessageCaption)


# --- caption rendering ---


def test_caption_handles_awkward_input():
    item = {"file_name": "{caption}{x}%s", "file_size": None, "caption": None}
    assert render_caption("{filename} {unknown} {", item).startswith("{x}%s")


def test_caption_is_trimmed():
    assert len(render_caption("x" * 5000, {})) == 1024


def test_size_formatting():
    assert delivery.format_size(None) == ""
    assert delivery.format_size(500) == "500 B"
    assert delivery.format_size(1536) == "1.5 KB"
    assert delivery.format_size(5 * 1024**3) == "5.0 GB"


# --- splitting ---


def items(*ids, channel=1):
    return [{"channel_id": channel, "message_id": i} for i in ids]


def test_runs_break_when_order_or_channel_changes():
    assert [len(r) for r in split_runs(items(1, 2, 3))] == [3]
    assert [len(r) for r in split_runs(items(3, 1, 2))] == [1, 2]
    assert [len(r) for r in split_runs(items(1) + items(2, channel=9))] == [1, 1]


def test_runs_respect_the_limit():
    assert [len(r) for r in split_runs(items(*range(1, 251)))] == [100, 100, 50]


def test_button_data_helper_is_usable():
    markup = InlineKeyboardMarkup(inline_keyboard=[])
    assert button_data(markup) == []
