"""The one place failures end up. Users get one calm sentence; details go to the logs."""

import html
import logging
import traceback

from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import ErrorEvent

from bot import texts
from bot.app import App

log = logging.getLogger(__name__)
DEV_MESSAGE_LIMIT = 3500


async def tell_user_something_went_wrong(event: ErrorEvent) -> None:
    update = event.update
    try:
        if update.callback_query:
            await update.callback_query.answer(texts.SOMETHING_WRONG, show_alert=True)
        elif update.message and update.message.chat.type == "private":
            await update.message.answer(texts.SOMETHING_WRONG)
    except Exception:
        log.info("Could not tell the user about a failure", exc_info=True)


async def tell_developer(app: App, event: ErrorEvent) -> None:
    if not app.config.dev_chat_id:
        return
    details = "".join(traceback.format_exception(event.exception))[-DEV_MESSAGE_LIMIT:]
    try:
        await app.bot.send_message(
            app.config.dev_chat_id,
            f"<pre>{html.escape(details)}</pre>",
        )
    except Exception:
        log.info("Could not notify the developer chat", exc_info=True)


async def on_error(event: ErrorEvent, app: App) -> bool:
    error = event.exception
    if isinstance(error, TelegramForbiddenError):
        # The user blocked the bot. Nothing to report and nobody to tell.
        log.info("User unreachable: %s", error)
        return True
    if isinstance(error, TelegramBadRequest) and "message is not modified" in str(error):
        return True
    log.error("Failed handling update %s", event.update.update_id, exc_info=error)
    await tell_user_something_went_wrong(event)
    await tell_developer(app, event)
    return True
