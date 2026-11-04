"""A command in the middle of a conversation always works and ends it cleanly."""

from bot import texts
from tests.helpers import OWNER_ID


async def test_genlink_during_batch_starts_genlink(world):
    await world.owner.send("/batch")
    await world.owner.send("/genlink")
    assert world.telegram.last_text(OWNER_ID) == texts.COLLECT_PROMPT


async def test_batch_during_genlink_starts_batch(world):
    await world.owner.send("/genlink")
    await world.owner.send("/batch")
    assert world.telegram.last_text(OWNER_ID) == texts.BATCH_FIRST


async def test_special_during_naming_shows_menu(world):
    await world.owner.tap("sp:new")
    await world.owner.send("/special_link")
    assert world.telegram.last_text(OWNER_ID) == texts.SPECIAL_MENU


async def test_command_with_bot_name_is_recognised(world):
    await world.owner.send("/genlink")
    await world.owner.send("/batch@store_bot")
    assert world.telegram.last_text(OWNER_ID) == texts.BATCH_FIRST


async def test_start_ends_a_conversation(world):
    await world.owner.send("/genlink")
    await world.owner.send("/start")
    await world.owner.send("not stored")
    assert world.telegram.last_text(OWNER_ID) == texts.UNKNOWN_MESSAGE
