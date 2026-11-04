"""Sends a link's stored messages to someone, applying the owner's settings."""

import asyncio
import logging
from dataclasses import dataclass

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot import texts
from bot.app import App

log = logging.getLogger(__name__)
CHUNK = 100
CAPTION_LIMIT = 1024
# Telegram asks for about one message per second in one chat.
PACE_SECONDS = 0.5
# Batch items have no known caption, and are sent in bulk so albums stay together.
BULK_GROUP = "bulk"


@dataclass
class Options:
    protect: bool
    caption: str | None
    button: dict | None


@dataclass
class Result:
    delivered: int
    total: int


def format_size(size: int | None) -> str:
    if not size:
        return ""
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return ""


def render_caption(template: str, item: dict) -> str:
    """Plain replacement, never str.format, so unusual characters in a caption or a
    file name can't break anything."""
    rendered = (
        template.replace("{filename}", item.get("file_name") or "")
        .replace("{filesize}", format_size(item.get("file_size")))
        .replace("{caption}", item.get("caption") or "")
    ).strip()
    return rendered[:CAPTION_LIMIT]


async def load_options(app: App) -> Options:
    return Options(
        protect=await app.settings.get("protect_content", False),
        caption=await app.settings.get("custom_caption"),
        button=await app.settings.get("custom_button"),
    )


def _markup(button: dict | None) -> InlineKeyboardMarkup | None:
    if not button:
        return None
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=button["text"], url=button["url"])]]
    )


def split_runs(items: list[dict]) -> list[list[dict]]:
    """Consecutive items that can go in one copyMessages call: same channel, strictly
    increasing ids (Telegram requires it), at most 100."""
    runs: list[list[dict]] = []
    for item in items:
        current = runs[-1] if runs else None
        if (
            current
            and current[-1]["channel_id"] == item["channel_id"]
            and current[-1]["message_id"] < item["message_id"]
            and len(current) < CHUNK
        ):
            current.append(item)
        else:
            runs.append([item])
    return runs


def _split_groups(items: list[dict]) -> list[list[dict]]:
    """Albums (and bulk items) stay together; everything else stands alone."""
    groups: list[list[dict]] = []
    for item in items:
        group_id = item.get("media_group_id")
        if groups and group_id and groups[-1][-1].get("media_group_id") == group_id:
            groups[-1].append(item)
        else:
            groups.append([item])
    return groups


async def _send_bulk(app: App, chat_id: int, run: list[dict], options: Options) -> list[int]:
    try:
        copies = await app.bot.copy_messages(
            chat_id=chat_id,
            from_chat_id=run[0]["channel_id"],
            message_ids=[item["message_id"] for item in run],
            protect_content=options.protect,
        )
        return [copy.message_id for copy in copies]
    except TelegramBadRequest as error:
        log.info("Could not copy a group of messages: %s", error)
        return []


async def _send_one(app: App, chat_id: int, item: dict, options: Options) -> bool:
    arguments = {}
    if options.caption and item.get("has_media"):
        arguments = {
            "caption": render_caption(options.caption, item),
            "parse_mode": None,
        }
    try:
        await app.bot.copy_message(
            chat_id=chat_id,
            from_chat_id=item["channel_id"],
            message_id=item["message_id"],
            protect_content=options.protect,
            reply_markup=_markup(options.button),
            **arguments,
        )
        return True
    except TelegramBadRequest as error:
        log.info("Could not copy message %s: %s", item["message_id"], error)
        return False


async def _send_album(app: App, chat_id: int, album: list[dict], options: Options) -> int:
    delivered = 0
    for run in split_runs(album):
        new_ids = await _send_bulk(app, chat_id, run, options)
        delivered += len(new_ids)
        if options.caption and len(new_ids) == len(run):
            for item, new_id in zip(run, new_ids, strict=True):
                if not item.get("has_media"):
                    continue
                try:
                    await app.bot.edit_message_caption(
                        chat_id=chat_id,
                        message_id=new_id,
                        caption=render_caption(options.caption, item),
                        parse_mode=None,
                    )
                except TelegramBadRequest as error:
                    # The file has arrived, and that's what matters.
                    log.info("Could not set a caption: %s", error)
    # Albums can't hold buttons, so the button follows in its own message.
    if options.button and delivered:
        await app.bot.send_message(
            chat_id, texts.DELIVERY_TAIL_BUTTON, reply_markup=_markup(options.button)
        )
    return delivered


async def deliver(app: App, chat_id: int, items: list[dict], options: Options) -> Result:
    """Raises TelegramForbiddenError if the person has blocked the bot."""
    delivered = 0
    if options.caption or options.button:
        for group in _split_groups(items):
            if group[0].get("media_group_id"):
                delivered += await _send_album(app, chat_id, group, options)
            else:
                delivered += int(await _send_one(app, chat_id, group[0], options))
            await asyncio.sleep(PACE_SECONDS)
    else:
        for run in split_runs(items):
            delivered += len(await _send_bulk(app, chat_id, run, options))
            await asyncio.sleep(PACE_SECONDS)
    return Result(delivered=delivered, total=len(items))
