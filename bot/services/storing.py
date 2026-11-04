"""Copies messages into the backup channel. Copying happens inside Telegram, so
files of any size work without being downloaded."""

import logging

from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import Message

from bot.app import App
from bot.db.links import Item

log = logging.getLogger(__name__)
CHUNK = 100  # Telegram's limit for one copyMessages call.

# Kinds of message Telegram can copy. Paid media, invoices and giveaways can't be.
COPYABLE = {
    "text",
    "animation",
    "audio",
    "document",
    "photo",
    "sticker",
    "video",
    "video_note",
    "voice",
    "contact",
    "location",
    "venue",
    "poll",
    "dice",
}
_ACCESS_PROBLEMS = (
    "chat not found",
    "rights",
    "not a member",
    "administrator",
    "kicked",
    "not enough",
)


class StorageBlockedError(Exception):
    """The bot can't post in the backup channel."""


def is_access_problem(error: Exception) -> bool:
    if isinstance(error, TelegramForbiddenError):
        return True
    return isinstance(error, TelegramBadRequest) and any(
        problem in str(error).lower() for problem in _ACCESS_PROBLEMS
    )


def is_copyable(message: Message) -> bool:
    return message.content_type in COPYABLE


def describe(message: Message) -> dict:
    """What we remember about a message before storing it."""
    media = (
        message.document
        or message.video
        or message.audio
        or message.animation
        or message.voice
        or (message.photo[-1] if message.photo else None)
    )
    return {
        "message_id": message.message_id,
        "media_group_id": message.media_group_id,
        "file_name": getattr(media, "file_name", None),
        "file_size": getattr(media, "file_size", None),
        "caption": message.caption,
        "has_media": media is not None,
    }


async def _copy_one(app: App, from_chat_id: int, message_id: int) -> int | None:
    try:
        copied = await app.bot.copy_message(
            chat_id=app.config.backup_channel_id,
            from_chat_id=from_chat_id,
            message_id=message_id,
        )
        return copied.message_id
    except (TelegramBadRequest, TelegramForbiddenError) as error:
        if is_access_problem(error):
            raise StorageBlockedError from error
        log.info("Skipping message %s: %s", message_id, error)
        return None


async def store_messages(app: App, from_chat_id: int, sources: list[dict]) -> list[Item]:
    """Returns pointers to the stored copies, in order. Groups of 100 keep albums intact."""
    channel_id = app.config.backup_channel_id
    ordered = sorted(sources, key=lambda source: source["message_id"])
    items: list[Item] = []
    for start in range(0, len(ordered), CHUNK):
        chunk = ordered[start : start + CHUNK]
        ids = [source["message_id"] for source in chunk]
        try:
            copies = await app.bot.copy_messages(
                chat_id=channel_id, from_chat_id=from_chat_id, message_ids=ids
            )
        except (TelegramBadRequest, TelegramForbiddenError) as error:
            if is_access_problem(error):
                raise StorageBlockedError from error
            copies = None
        if copies is not None and len(copies) == len(ids):
            new_ids = [copy.message_id for copy in copies]
        else:
            # Telegram skipped something (usually a deleted message) without saying
            # which, so copy one at a time to keep each message's details correct.
            new_ids = [await _copy_one(app, from_chat_id, message_id) for message_id in ids]
        for source, new_id in zip(chunk, new_ids, strict=True):
            if new_id is None:
                continue
            details = {k: v for k, v in source.items() if k != "message_id"}
            items.append(Item(channel_id=channel_id, message_id=new_id, **details))
    return items
