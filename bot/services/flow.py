"""What happens when somebody opens a link."""

import logging

from aiogram.exceptions import TelegramForbiddenError

from bot import texts
from bot.app import App
from bot.db.links import is_valid_code
from bot.services import delivery, gate

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
    if not is_valid_code(code) or await app.links.get(code) is None:
        await app.bot.send_message(user_id, texts.LINK_GONE)
        return
    if bypass_gate:
        await deliver_code(app, user_id, code)
        return
    pending, total = await gate.pending_targets(app, user_id)
    if not pending:
        await app.users.set_pending(user_id, None)
        await deliver_code(app, user_id, code)
        return
    # Opening another link part way through simply replaces what they're waiting for.
    await app.users.set_pending(user_id, code)
    text, markup = gate.render_screen(pending, total)
    await app.bot.send_message(user_id, text, reply_markup=markup)


async def continue_flow(app: App, user_id: int, show_screen: bool = True) -> bool:
    """After someone completes a step. Returns True if there's nothing left to do."""
    code = await app.users.get_pending(user_id)
    if code is None:
        return True
    pending, total = await gate.pending_targets(app, user_id)
    if pending:
        if show_screen:
            text, markup = gate.render_screen(pending, total)
            await app.bot.send_message(user_id, text, reply_markup=markup)
        return False
    await app.users.set_pending(user_id, None)
    await deliver_code(app, user_id, code)
    return True
