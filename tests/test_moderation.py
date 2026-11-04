from aiogram.methods import DeleteMyCommands, SetMyCommands
from aiogram.types import MessageOriginUser, User

from bot import texts
from bot.db.roles import Role
from bot.menus import commands_for
from tests.helpers import OWNER_ID


def names(commands):
    return {c.command for c in commands}


def test_menus_separate_roles():
    assert names(commands_for(Role.USER)) == {"start"}
    moderator = names(commands_for(Role.MODERATOR))
    assert "settings" not in moderator and {"genlink", "ban", "broadcast"} <= moderator
    assert "settings" in names(commands_for(Role.OWNER))


def test_every_required_command_is_on_the_owner_menu():
    required = {
        "start",
        "genlink",
        "universal_link",
        "batch",
        "special_link",
        "shortener",
        "settings",
        "broadcast",
        "ban",
        "unban",
    }
    assert required <= names(commands_for(Role.OWNER))


async def test_owner_bans_and_user_is_stopped_then_unbanned(world):
    user = world.person(5, "bad")
    await user.send("hello")
    await world.owner.send("/ban @bad")
    assert world.telegram.last_text(OWNER_ID) == texts.BANNED_OK.format(user_id=5)
    await user.send("hello again")
    assert world.telegram.last_text(5) == texts.BANNED
    await world.owner.send("/unban 5")
    await user.send("back")
    assert world.telegram.last_text(5) == texts.UNKNOWN_MESSAGE


async def test_ordinary_user_cannot_ban(world):
    await world.person(6, "x").send("/ban 7")
    assert world.telegram.last_text(6) == texts.UNKNOWN_MESSAGE
    assert not await world.app.users.is_banned(7)


async def test_owner_cannot_be_banned_by_a_moderator(world):
    await world.app.roles.add_by_username("mod", OWNER_ID)
    mod = world.person(8, "mod")
    await mod.send(f"/ban {OWNER_ID}")
    assert world.telegram.last_text(8) == texts.CANT_BAN_OWNER
    assert not await world.app.users.is_banned(OWNER_ID)


async def test_moderators_cannot_ban_each_other(world):
    await world.app.roles.add_by_username("mod1", OWNER_ID)
    await world.app.roles.add_by_username("mod2", OWNER_ID)
    await world.person(8, "mod1").send("/start-ish")
    await world.person(9, "mod2").send("/start-ish")
    await world.person(8, "mod1").send("/ban @mod2")
    assert world.telegram.last_text(8) == texts.CANT_BAN_STAFF


async def test_ban_with_nothing_shows_how(world):
    await world.owner.send("/ban")
    assert world.telegram.last_text(OWNER_ID) == texts.BAN_USAGE
    await world.owner.send("/unban")
    assert world.telegram.last_text(OWNER_ID) == texts.UNBAN_USAGE


async def test_unknown_username_is_explained(world):
    await world.owner.send("/ban @nobodyhere")
    assert world.telegram.last_text(OWNER_ID) == texts.USER_NOT_FOUND


async def test_ban_by_id_for_someone_new_applies_when_they_arrive(world):
    await world.owner.send("/ban 77")
    await world.person(77, "late").send("hi")
    assert world.telegram.last_text(77) == texts.BANNED


async def test_double_ban_and_unban_say_so(world):
    await world.owner.send("/ban 5")
    await world.owner.send("/ban 5")
    assert world.telegram.last_text(OWNER_ID) == texts.ALREADY_BANNED.format(user_id=5)
    await world.owner.send("/unban 5")
    await world.owner.send("/unban 5")
    assert world.telegram.last_text(OWNER_ID) == texts.NOT_BANNED.format(user_id=5)


async def test_ban_by_replying_to_a_forwarded_message(world):
    original = User(id=33, is_bot=False, first_name="T")
    forwarded = world.owner.message(
        text="fwd",
        forward_origin=MessageOriginUser(date=0, sender_user=original),
    )
    await world.owner.send("/ban", reply_to_message=forwarded)
    assert await world.app.users.is_banned(33)


async def test_group_messages_are_ignored(world):
    from aiogram.types import Chat

    group = Chat(id=-5, type="supergroup")
    await world.owner.send("/ban 5", chat=group)
    assert world.telegram.calls == []
    assert not await world.app.users.is_banned(5)


async def test_moderator_gets_their_menu_on_first_contact(world):
    await world.app.roles.add_by_username("newmod", OWNER_ID)
    await world.person(8, "newmod").send("hello")
    commands = world.telegram.of(SetMyCommands)[-1]
    assert commands.scope.chat_id == 8
    assert "ban" in names(commands.commands) and "settings" not in names(commands.commands)


async def test_removed_moderator_loses_menu_and_powers(world):
    await world.app.roles.add_by_username("exmod", OWNER_ID)
    exmod = world.person(8, "exmod")
    await exmod.send("/ban 5")
    assert await world.app.users.is_banned(5)
    await world.app.users.set_banned(5, False)
    moderator = (await world.app.roles.list_moderators())[0]
    await world.app.roles.remove(moderator["id"])
    await exmod.send("/ban 5")
    assert not await world.app.users.is_banned(5)
    assert world.telegram.of(DeleteMyCommands)


async def test_failure_shows_only_the_calm_message(world, monkeypatch):
    async def explode(*args, **kwargs):
        raise RuntimeError("psycopg connection to 10.0.0.1 failed with code 500")

    monkeypatch.setattr(world.app.users, "is_banned", explode)
    await world.owner.send("/ban 5")
    assert world.telegram.last_text(OWNER_ID) == texts.SOMETHING_WRONG


async def test_failure_in_a_button_shows_calm_alert(world, monkeypatch):
    from aiogram.methods import AnswerCallbackQuery

    async def explode(*args, **kwargs):
        raise RuntimeError("boom")

    user = world.person(5)
    monkeypatch.setattr(world.app.roles, "resolve", explode)
    await user.tap("whatever")
    answer = world.telegram.of(AnswerCallbackQuery)[-1]
    assert answer.text == texts.SOMETHING_WRONG


async def test_developer_chat_gets_details_but_user_does_not(world, monkeypatch):
    world.app.config.dev_chat_id = 999

    async def explode(*args, **kwargs):
        raise RuntimeError("secret detail")

    monkeypatch.setattr(world.app.users, "is_banned", explode)
    await world.owner.send("/ban 5")
    assert "secret detail" in world.telegram.last_text(999)
    assert "secret detail" not in world.telegram.last_text(OWNER_ID)


async def test_old_buttons_are_answered_politely(world):
    from aiogram.methods import AnswerCallbackQuery

    await world.person(5).tap("no:such:button")
    assert world.telegram.of(AnswerCallbackQuery)[-1].text == texts.BUTTON_EXPIRED
