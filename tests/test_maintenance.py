from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.methods import CreateChatInviteLink, EditChatInviteLink, SendDocument

from bot import texts
from bot.db.targets import TELEGRAM, YOUTUBE
from bot.services import backup, maintenance
from tests.helpers import OWNER_ID


async def add_private(world):
    target, _ = await world.app.targets.add(
        TELEGRAM, "-1", "Private", "https://t.me/+old", chat_id=-1
    )
    return target


async def test_working_links_are_left_alone(world):
    target = await add_private(world)
    await maintenance.refresh_invite_links(world.app)
    assert (await world.app.targets.get(target["id"]))["url"] == "https://t.me/+old"
    assert not world.telegram.of(CreateChatInviteLink)


async def test_revoked_link_is_replaced(world):
    target = await add_private(world)
    world.telegram.set(EditChatInviteLink, TelegramBadRequest(EditChatInviteLink, "revoked"))
    await maintenance.refresh_invite_links(world.app)
    assert (await world.app.targets.get(target["id"]))["url"] == "https://t.me/+newlink"


async def test_public_and_social_targets_are_skipped(world):
    await world.app.targets.add(TELEGRAM, "-2", "Public", "https://t.me/pub", chat_id=-2)
    await world.app.targets.add(YOUTUBE, "@a", "A", "https://youtube.com/@a")
    await maintenance.refresh_invite_links(world.app)
    assert not world.telegram.of(EditChatInviteLink)


async def test_lost_access_tells_the_owner_once(world):
    await add_private(world)
    world.telegram.set(EditChatInviteLink, TelegramForbiddenError(EditChatInviteLink, "kicked"))
    await maintenance.refresh_invite_links(world.app)
    await maintenance.refresh_invite_links(world.app)
    assert world.telegram.texts_to(OWNER_ID) == [texts.FS_CHAT_NOTICE.format(name="Private")]


async def test_daily_run_backs_up_then_waits(world):
    await add_private(world)
    await maintenance.run_once(world.app)
    await maintenance.run_once(world.app)
    assert len(world.telegram.of(SendDocument)) == 1
    assert len(world.telegram.of(EditChatInviteLink)) == 1
    assert await world.app.settings.get(backup.LAST_BACKUP)
