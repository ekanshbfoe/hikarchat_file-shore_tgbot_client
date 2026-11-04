"""What happens when somebody opens a link."""

import logging

from aiogram.exceptions import TelegramForbiddenError

from bot import texts
from bot.app import App
from bot.services import delivery

log = logging.getLogger(__name__)


async def deliver_code(app: App, user_id: int, code: str) -> None:
    link = await app.links.get(code)
    if link is None:
        await app.bot.send_message(user_id, texts.LINK_GONE)
        return
    options = await delivery.load_options(app)
    try:
        result = await delivery.deliver(app, user_id, link["items"], options)
        if result.delivered == 0:
            await app.bot.send_message(user_id, texts.FILES_GONE)
        elif result.delivered < result.total:
            await app.bot.send_message(user_id, texts.SOME_FILES_GONE)
    except TelegramForbiddenError:
        await app.users.deactivate(user_id)


async def open_link(app: App, user_id: int, code: str, bypass_gate: bool) -> None:
    await deliver_code(app, user_id, code)
