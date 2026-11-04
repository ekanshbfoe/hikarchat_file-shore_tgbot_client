from aiogram.methods import AnswerCallbackQuery, CopyMessages

from bot import texts
from bot.db.links import Item
from tests.fake_telegram import button_data
from tests.helpers import OWNER_ID

BACKUP = -100500


async def make(world, *ids, title="Pack"):
    return await world.app.links.create(
        "special",
        OWNER_ID,
        [Item(channel_id=BACKUP, message_id=i, file_name=f"f{i}") for i in ids],
        title=title,
    )


async def ids_of(world, code):
    return [i["message_id"] for i in (await world.app.links.get(code))["items"]]


async def version(world, code):
    return (await world.app.links.get(code))["version"]


async def test_create_flow(world):
    await world.owner.send("/special_link")
    assert "sp:new" in button_data(world.telegram.last_markup(OWNER_ID))
    await world.owner.tap("sp:new")
    await world.owner.send("My Pack")
    await world.owner.send("content")
    await world.owner.tap("collect:done")
    code = world.telegram.last_text(OWNER_ID).rsplit("start=", 1)[1]
    link = await world.app.links.get(code)
    assert link["kind"] == "special" and link["title"] == "My Pack" and len(link["items"]) == 1


async def test_name_is_validated(world):
    await world.owner.tap("sp:new")
    await world.owner.send("x" * 61)
    assert world.telegram.last_text(OWNER_ID) == texts.SPECIAL_NAME_INVALID
    await world.owner.send(sticker=None, text=None)
    assert world.telegram.last_text(OWNER_ID) == texts.SPECIAL_NAME_INVALID


async def test_add_keeps_the_same_link(world):
    code = await make(world, 1)
    await world.owner.tap(f"sp:add:{code}")
    await world.owner.send("more")
    await world.owner.tap("collect:done")
    assert len(await ids_of(world, code)) == 2
    assert code in world.telegram.last_text(OWNER_ID)


async def test_edit_is_visible_to_people_at_once(world):
    code = await make(world, 1, 2)
    await world.person(5).send(f"/start {code}")
    await world.owner.tap(f"sp:rm:{code}:0:{await version(world, code)}")
    world.telegram.clear()
    await world.person(5).send(f"/start {code}")
    assert world.telegram.of(CopyMessages)[0].message_ids == [2]


async def test_reorder(world):
    code = await make(world, 1, 2, 3)
    await world.owner.tap(f"sp:dn:{code}:0:{await version(world, code)}")
    assert await ids_of(world, code) == [2, 1, 3]
    await world.owner.tap(f"sp:up:{code}:2:{await version(world, code)}")
    assert await ids_of(world, code) == [2, 3, 1]


async def test_reordered_link_is_delivered_in_new_order(world):
    code = await make(world, 1, 2)
    await world.owner.tap(f"sp:dn:{code}:0:{await version(world, code)}")
    world.telegram.clear()
    await world.person(5).send(f"/start {code}")
    sent = [c.message_ids for c in world.telegram.of(CopyMessages)]
    assert sent == [[2], [1]]  # Telegram needs increasing ids, so they go separately.


async def test_moving_past_the_ends_does_nothing(world):
    code = await make(world, 1, 2)
    start = await version(world, code)
    await world.owner.tap(f"sp:up:{code}:0:{start}")
    await world.owner.tap(f"sp:dn:{code}:1:{start}")
    await world.owner.tap(f"sp:rm:{code}:9:{start}")
    assert await ids_of(world, code) == [1, 2] and await version(world, code) == start


async def test_second_editor_is_told_to_refresh(world):
    code = await make(world, 1, 2)
    old = await version(world, code)
    await world.owner.tap(f"sp:rm:{code}:0:{old}")
    await world.owner.tap(f"sp:rm:{code}:0:{old}")
    assert await ids_of(world, code) == [2]
    assert world.telegram.of(AnswerCallbackQuery)[-1].text == texts.SPECIAL_STALE


async def test_delete_needs_confirmation(world):
    code = await make(world, 1)
    await world.owner.tap(f"sp:del:{code}")
    assert await world.app.links.get(code) is not None
    await world.owner.tap(f"sp:delyes:{code}")
    assert await world.app.links.get(code) is None
    await world.person(5).send(f"/start {code}")
    assert world.telegram.last_text(5) == texts.LINK_GONE


async def test_deleted_link_buttons_are_polite(world):
    code = await make(world, 1)
    await world.app.links.delete(code)
    await world.owner.tap(f"sp:open:{code}")
    assert world.telegram.of(AnswerCallbackQuery)[-1].text == texts.LINK_GONE


async def test_emptied_link_tells_people(world):
    code = await make(world, 1)
    await world.owner.tap(f"sp:rm:{code}:0:{await version(world, code)}")
    await world.person(5).send(f"/start {code}")
    assert world.telegram.last_text(5) == texts.FILES_GONE


async def test_ordinary_user_cannot_touch_special_links(world):
    code = await make(world, 1, 2)
    user = world.person(5)
    await user.send("/special_link")
    assert world.telegram.last_text(5) == texts.UNKNOWN_MESSAGE
    await user.tap(f"sp:rm:{code}:0:{await version(world, code)}")
    assert await ids_of(world, code) == [1, 2]


async def test_normal_links_cant_be_edited_through_special_buttons(world):
    code = await world.app.links.create(
        "genlink", OWNER_ID, [Item(channel_id=BACKUP, message_id=1)]
    )
    await world.owner.tap(f"sp:rm:{code}:0:1")
    assert await ids_of(world, code) == [1]


async def test_titles_are_escaped(world):
    code = await make(world, 1, title="<x>&")
    await world.owner.tap(f"sp:open:{code}")
    assert "&lt;x&gt;&amp;" in world.telegram.of_edit_text(-1)
