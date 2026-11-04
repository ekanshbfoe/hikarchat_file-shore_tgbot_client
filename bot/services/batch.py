"""Copies a range of channel posts into the backup channel, in the background."""

import asyncio
import logging
import re

from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import Message

from bot import texts
from bot.app import App
from bot.db.jobs import DONE, FAILED
from bot.db.links import Item
from bot.services import share
from bot.services.delivery import BULK_GROUP
from bot.services.storing import CHUNK, is_access_problem

log = logging.getLogger(__name__)
KIND = "batch"
MAX_POSTS = 5000
PACE_SECONDS = 1.0

_PRIVATE_LINK = re.compile(r"^(?:https?://)?t(?:elegram)?\.me/c/(\d+)/(?:\d+/)?(\d+)/?(?:\?.*)?$")
_PUBLIC_LINK = re.compile(
    r"^(?:https?://)?t(?:elegram)?\.me/([A-Za-z][A-Za-z0-9_]{3,})/(?:\d+/)?(\d+)/?(?:\?.*)?$"
)


async def parse_post(app: App, message: Message) -> tuple[int, int] | None:
    """Work out (channel id, post id) from a forwarded post or a post link."""
    origin = message.forward_origin
    if origin is not None and origin.type == "channel":
        return origin.chat.id, origin.message_id
    text = (message.text or "").strip()
    match = _PRIVATE_LINK.match(text)
    if match:
        return int(f"-100{match.group(1)}"), int(match.group(2))
    match = _PUBLIC_LINK.match(text)
    if match:
        try:
            chat = await app.bot.get_chat(f"@{match.group(1)}")
        except (TelegramBadRequest, TelegramForbiddenError):
            return None
        return chat.id, int(match.group(2))
    return None


async def check_source(app: App, channel_id: int) -> str | None:
    """Returns a message for the person if the channel can't be used."""
    try:
        chat = await app.bot.get_chat(channel_id)
        member = await app.bot.get_chat_member(channel_id, app.bot.id)
    except (TelegramBadRequest, TelegramForbiddenError):
        return texts.BATCH_NOT_ADMIN
    if member.status not in ("administrator", "creator"):
        return texts.BATCH_NOT_ADMIN
    if chat.has_protected_content:
        return texts.BATCH_PROTECTED
    return None


async def _say(app: App, job: dict, text: str) -> None:
    payload = job["payload"]
    try:
        await app.bot.edit_message_text(
            text=text, chat_id=payload["chat_id"], message_id=payload["progress_id"]
        )
    except TelegramBadRequest:
        # The progress message was deleted, or already says this.
        if text != texts.BATCH_PROGRESS:
            log.debug("Could not update batch progress")
    except TelegramForbiddenError:
        log.info("Batch owner unreachable")


async def run(app: App, job: dict) -> None:
    payload = job["payload"]
    source, last, code = payload["source"], payload["last"], payload["code"]
    cursor = max(job["cursor"], payload["first"] - 1)
    stored = job["stats"].get("stored", 0)
    total = last - payload["first"] + 1

    while cursor < last:
        ids = list(range(cursor + 1, min(cursor + CHUNK, last) + 1))
        try:
            copies = await app.bot.copy_messages(
                chat_id=app.config.backup_channel_id, from_chat_id=source, message_ids=ids
            )
        except (TelegramBadRequest, TelegramForbiddenError) as error:
            if is_access_problem(error):
                await app.links.delete(code)
                await app.jobs.finish(job["id"], FAILED)
                await _say(app, job, texts.BATCH_FAILED)
                return
            log.info("Skipping a range of posts: %s", error)
            copies = []
        items = [
            Item(
                channel_id=app.config.backup_channel_id,
                message_id=copy.message_id,
                media_group_id=BULK_GROUP,
            )
            for copy in copies
        ]
        await app.links.append(code, items)
        stored += len(items)
        cursor = ids[-1]
        await app.jobs.save_progress(job["id"], cursor, {"stored": stored})
        await _say(
            app,
            job,
            texts.BATCH_PROGRESS.format(done=cursor - payload["first"] + 1, total=total),
        )
        await asyncio.sleep(PACE_SECONDS)

    await app.jobs.finish(job["id"], DONE)
    if stored == 0:
        await app.links.delete(code)
        await _say(app, job, texts.BATCH_EMPTY)
        return
    await _say(
        app, job, texts.BATCH_DONE.format(count=stored, link=await share.share_link(app, code))
    )
