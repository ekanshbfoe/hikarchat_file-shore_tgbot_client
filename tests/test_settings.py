import gzip
import json

from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.fsm.storage.base import StorageKey
from aiogram.methods import AnswerCallbackQuery, DeleteMessage, DeleteMyCommands, SendDocument

from bot import texts
from bot.db.links import Item
from bot.handlers import settings as handler
from bot.services import backup
from tests.fake_telegram import bot_admin, button_data, button_urls
from tests.helpers import OWNER_ID


async def test_owner_sees_every_button_from_the_client_screenshot(world):
    await world.owner.send("/settings")
    assert world.telegram.last_text(OWNER_ID) == texts.SETTINGS_TITLE
    data = button_data(world.telegram.last_markup(OWNER_ID))
    assert {"set:backup", "set:short", "set:caption", "set:button", "set:protect"} <= set(data)
    assert {"fs:home", "set:mods"} <= set(data)


async def test_moderators_and_users_cant_open_settings(world):
    await world.app.roles.add_by_username("m", OWNER_ID)
    for person, chat in ((world.person(8, "m"), 8), (world.person(5), 5)):
        await person.send("/settings")
        assert world.telegram.last_text(chat) == texts.UNKNOWN_MESSAGE


async def test_moderators_cant_press_settings_buttons(world):
    await world.app.roles.add_by_username("m", OWNER_ID)
    await world.person(8, "m").tap("set:protect")
    assert await world.app.settings.get("protect_content", False) is False


async def test_protect_toggle(world):
    await world.owner.tap("set:protect")
    assert await world.app.settings.get("protect_content") is True
    await world.owner.tap("set:protect")
    assert await world.app.settings.get("protect_content") is False


async def test_caption_set_validate_remove(world):
    await world.owner.tap("set:caption:edit")
    await world.owner.send("x" * 1001)
    assert world.telegram.last_text(OWNER_ID) == texts.CAPTION_TOO_LONG
    await world.owner.send("{filename} <b>")
    assert await world.app.settings.get("custom_caption") == "{filename} <b>"
    assert "&lt;b&gt;" in world.telegram.last_text(OWNER_ID)
    await world.owner.tap("set:caption:rm")
    assert not await world.app.settings.get("custom_caption")


async def test_button_set_validate_remove(world):
    await world.owner.tap("set:button:edit")
    await world.owner.send("no link here")
    assert world.telegram.last_text(OWNER_ID) == texts.BUTTON_INVALID
    await world.owner.send("Join - javascript:alert(1)")
    assert world.telegram.last_text(OWNER_ID) == texts.BUTTON_INVALID
    await world.owner.send("Join us - now - https://t.me/x")
    assert await world.app.settings.get("custom_button") == {
        "text": "Join us - now",
        "url": "https://t.me/x",
    }
    await world.owner.tap("set:button:rm")
    assert not await world.app.settings.get("custom_button")


async def test_removed_caption_and_button_stop_being_applied(world):
    from aiogram.methods import CopyMessage, CopyMessages

    await world.owner.tap("set:button:rm")
    await world.owner.tap("set:caption:rm")
    code = await world.app.links.create(
        "genlink", OWNER_ID, [Item(channel_id=-1, message_id=1, has_media=True)]
    )
    await world.person(5).send(f"/start {code}")
    assert world.telegram.of(CopyMessages) and not world.telegram.of(CopyMessage)


async def test_shortener_setup_checks_details_and_hides_key(world, monkeypatch):
    results = iter([None, "https://s.io/ok"])

    async def fake(url, site, key):
        return next(results)

    monkeypatch.setattr(handler, "shorten", fake)
    await world.owner.tap("set:short:edit")
    await world.owner.send("nope")
    assert world.telegram.last_text(OWNER_ID) == texts.SHORTENER_SITE_INVALID
    await world.owner.send("https://short.example.com/")
    await world.owner.send("wrongkey")
    assert world.telegram.of(DeleteMessage)
    assert texts.SHORTENER_CHECK_FAILED in world.telegram.last_text(OWNER_ID)
    assert not await world.app.settings.get("shortener")
    await world.owner.send("short.example.com")
    await world.owner.send("rightkey")
    assert world.telegram.last_text(OWNER_ID) == texts.SHORTENER_SAVED
    assert await world.app.settings.get("shortener") == {
        "site": "short.example.com",
        "key": "rightkey",
        "enabled": True,
    }


async def test_shortener_key_is_never_shown(world):
    await world.app.settings.set("shortener", {"site": "s.io", "key": "SECRETKEY", "enabled": True})
    await world.owner.tap("set:short")
    assert "SECRETKEY" not in world.telegram.of_edit_text(-1)


async def test_shortener_toggle_and_remove(world):
    await world.app.settings.set("shortener", {"site": "s.io", "key": "k", "enabled": True})
    await world.owner.tap("set:short:toggle")
    assert (await world.app.settings.get("shortener"))["enabled"] is False
    await world.owner.tap("set:short:rm")
    assert not await world.app.settings.get("shortener")
    await world.owner.tap("set:short:toggle")  # An old button after removal.


async def test_update_channel_appears_on_welcome(world):
    await world.owner.tap("set:update:edit")
    await world.owner.send("hello")
    assert world.telegram.last_text(OWNER_ID) == texts.SHORTENER_BAD_LINK
    await world.owner.send("@mychannel")
    assert await world.app.settings.get("update_channel") == "https://t.me/mychannel"
    await world.person(5).send("/start")
    assert "https://t.me/mychannel" in button_urls(world.telegram.last_markup(5))
    await world.owner.tap("set:update:rm")
    await world.person(5).send("/start")
    assert button_urls(world.telegram.last_markup(5)) == []


async def test_add_and_remove_moderator(world):
    await world.owner.tap("set:mods:add")
    await world.owner.send("not valid!")
    assert world.telegram.last_text(OWNER_ID) == texts.MODERATOR_INVALID
    await world.owner.send("@new_mod")
    assert "@new_mod" in world.telegram.last_text(OWNER_ID)
    await world.owner.tap("set:mods:add")
    await world.owner.send("new_mod")
    assert texts.MODERATOR_ALREADY in world.telegram.texts_to(OWNER_ID)

    mod = world.person(8, "new_mod")
    await mod.send("/genlink")
    assert world.telegram.last_text(8) == texts.COLLECT_PROMPT

    moderator = (await world.app.roles.list_moderators())[0]
    await world.owner.tap(f"set:mods:rm:{moderator['id']}")
    assert world.telegram.of(DeleteMyCommands)
    key = StorageKey(bot_id=world.app.bot.id, chat_id=8, user_id=8)
    assert await world.dispatcher.storage.get_state(key) is None

    await mod.send("/genlink")
    assert world.telegram.last_text(8) == texts.UNKNOWN_MESSAGE
    await mod.send("anything")
    assert world.telegram.last_text(8) == texts.UNKNOWN_MESSAGE


async def test_owner_cannot_be_added_as_moderator(world):
    await world.owner.send("hi")
    await world.owner.tap("set:mods:add")
    await world.owner.send("@owner_name")
    assert texts.MODERATOR_IS_OWNER in world.telegram.texts_to(OWNER_ID)


async def test_double_tap_with_same_content_is_silent(world):
    from aiogram.methods import EditMessageText

    world.telegram.set(
        EditMessageText, TelegramBadRequest(EditMessageText, "message is not modified")
    )
    await world.owner.tap("set:home")
    assert texts.SOMETHING_WRONG not in [
        call.text for call in world.telegram.of(AnswerCallbackQuery)
    ]


# --- backup ---


async def test_backup_goes_to_the_channel_without_secrets(world):
    await world.app.settings.set("shortener", {"site": "s", "key": "SECRET", "enabled": True})
    await world.app.settings.set("custom_caption", "hello")
    code = await world.app.links.create("genlink", OWNER_ID, [Item(channel_id=-1, message_id=7)])
    await world.owner.tap("set:backup:now")
    sent = world.telegram.of(SendDocument)[0]
    assert sent.chat_id == world.app.config.backup_channel_id
    content = json.loads(gzip.decompress(sent.document.data))
    assert "SECRET" not in json.dumps(content)
    assert content["settings"]["custom_caption"] == "hello"
    assert content["links"][0]["code"] == code
    assert content["links"][0]["items"] == [[-1, 7]]
    assert world.telegram.of(AnswerCallbackQuery)[-1].text == texts.BACKUP_DONE
    assert await world.app.settings.get(backup.LAST_BACKUP)


async def test_blocked_channel_explained_on_manual_backup(world):
    world.telegram.set(SendDocument, TelegramForbiddenError(SendDocument, "kicked"))
    await world.owner.tap("set:backup:now")
    assert world.telegram.of(AnswerCallbackQuery)[-1].text == texts.BACKUP_FAILED


async def test_daily_backup_only_when_due_and_nags_once(world):
    await backup.backup_if_due(world.app)
    await backup.backup_if_due(world.app)
    assert len(world.telegram.of(SendDocument)) == 1

    await world.app.settings.set(backup.LAST_BACKUP, "2020-01-01T00:00:00+00:00")
    world.telegram.set(SendDocument, TelegramForbiddenError(SendDocument, "kicked"))
    await backup.backup_if_due(world.app)
    await backup.backup_if_due(world.app)
    assert world.telegram.texts_to(OWNER_ID) == [texts.BACKUP_CHANNEL_NOTICE]


async def test_startup_check_reports_missing_access_once(world):
    from aiogram.methods import GetChatMember

    world.telegram.set(GetChatMember, lambda m: bot_admin())
    assert await backup.check_backup_channel(world.app)
    assert world.telegram.texts_to(OWNER_ID) == []

    world.telegram.set(GetChatMember, TelegramBadRequest(GetChatMember, "chat not found"))
    assert not await backup.check_backup_channel(world.app)
    assert not await backup.check_backup_channel(world.app)
    assert world.telegram.texts_to(OWNER_ID) == [texts.BACKUP_CHANNEL_NOTICE]
