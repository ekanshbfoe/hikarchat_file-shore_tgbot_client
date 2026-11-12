"""The command menu each role sees in Telegram."""

from aiogram.methods import DeleteMyCommands, SetMyCommands

from bot.db.roles import Role
from bot.menus import MENU_TTL, OWNER_MENU_TTL, clear_menu, set_default_menu, sync_menu
from tests.helpers import OWNER_ID

OWNER_COMMANDS = {"start", "genlink", "settings", "broadcast", "cancel"}


def set_calls(telegram):
    return telegram.of(SetMyCommands)


def chat_scopes(telegram):
    return {call.scope.chat_id for call in set_calls(telegram) if hasattr(call.scope, "chat_id")}


def sent_commands(telegram, chat_id):
    for call in reversed(set_calls(telegram)):
        if getattr(call.scope, "chat_id", None) == chat_id:
            return {command.command for command in call.commands}
    return set()


async def test_startup_gives_every_owner_their_menu(world, monkeypatch):
    world.app.config.extra_owner_ids = [2000]
    world.telegram.clear()

    await set_default_menu(world.app)

    assert OWNER_ID in chat_scopes(world.telegram)
    assert 2000 in chat_scopes(world.telegram)
    assert sent_commands(world.telegram, 2000) >= OWNER_COMMANDS


async def test_startup_survives_an_owner_who_has_not_opened_the_bot(world):
    from aiogram.exceptions import TelegramBadRequest

    def refuse_chat_scope(method):
        if getattr(method.scope, "chat_id", None):
            raise TelegramBadRequest(method=method, message="chat not found")
        return True

    world.telegram.set(SetMyCommands, refuse_chat_scope)

    await set_default_menu(world.app)  # must not raise

    assert set_calls(world.telegram)


async def test_owner_menu_is_set_on_their_first_message(world):
    world.telegram.clear()

    await sync_menu(world.app, OWNER_ID, Role.OWNER)

    assert sent_commands(world.telegram, OWNER_ID) >= OWNER_COMMANDS


async def test_a_moderator_menu_is_set_once_then_left_alone(world):
    world.app.roles.owner_ids = frozenset({OWNER_ID})
    world.telegram.clear()

    await sync_menu(world.app, 5, Role.MODERATOR)
    await sync_menu(world.app, 5, Role.MODERATOR)

    assert len(set_calls(world.telegram)) == 1


async def test_removing_a_moderator_takes_their_commands_away(world):
    world.telegram.clear()

    await clear_menu(world.app, 5)

    assert world.telegram.of(DeleteMyCommands)
    assert sent_commands(world.telegram, 5) == set()


async def test_removing_an_owner_keeps_their_menu(world):
    world.telegram.clear()

    await clear_menu(world.app, OWNER_ID)

    assert not world.telegram.of(DeleteMyCommands)
    assert sent_commands(world.telegram, OWNER_ID) >= OWNER_COMMANDS


async def test_owner_menu_expires_sooner_than_other_menus():
    assert OWNER_MENU_TTL < MENU_TTL
