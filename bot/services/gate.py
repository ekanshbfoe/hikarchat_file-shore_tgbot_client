"""Force subscribe: works out what someone still has to do, and shows them."""

import asyncio
import logging

from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramNetworkError,
    TelegramServerError,
)
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot import texts
from bot.app import App
from bot.db.targets import SOCIAL, TELEGRAM, TIKTOK, YOUTUBE
from bot.services.notices import notify_owner_once

log = logging.getLogger(__name__)
MEMBER_CACHE_SECONDS = 300.0
_JOINED = {"creator", "administrator", "member"}


async def _is_telegram_satisfied(app: App, user_id: int, target: dict) -> bool:
    cache_key = f"member:{user_id}:{target['id']}"
    found, _, fresh = await app.store.cache.get(cache_key)
    if found and fresh:
        return True
    try:
        member = await app.bot.get_chat_member(target["chat_id"], user_id)
    except (TelegramBadRequest, TelegramForbiddenError):
        # Removed or demoted: we can't tell, and the person shouldn't pay for that.
        log.warning("Cannot check target %s", target["id"])
        await notify_owner_once(
            app,
            f"target:{target['id']}",
            texts.FS_CHAT_NOTICE.format(name=texts.esc(target["display_name"])),
        )
        return True
    except (TelegramNetworkError, TelegramServerError):
        log.warning("Telegram unavailable while checking target %s", target["id"])
        return True
    if member.status == "kicked":
        return True  # Banned from that chat, so they could never join it.
    joined = member.status in _JOINED or (
        member.status == "restricted" and getattr(member, "is_member", False)
    )
    if joined:
        await app.store.cache.set(cache_key, True, MEMBER_CACHE_SECONDS)
    return joined


async def pending_targets(app: App, user_id: int) -> tuple[list[dict], int]:
    """Recalculated at every step, so changes the owner makes apply at once.
    Returns (still to do, total required)."""
    targets = await app.targets.list_active()
    if not targets:
        return [], 0
    verified = await app.targets.verified_versions(user_id)
    unverified = [
        target for target in targets if verified.get(str(target["id"])) != target["version"]
    ]
    telegram = [target for target in unverified if target["platform"] == TELEGRAM]
    # Telegram answers one chat at a time, so asking in turn makes somebody who must
    # join three channels wait three times as long as they have to.
    joined = await asyncio.gather(
        *(_is_telegram_satisfied(app, user_id, target) for target in telegram)
    )
    satisfied = {target["id"] for target, done in zip(telegram, joined, strict=True) if done}
    pending = [target for target in unverified if target["id"] not in satisfied]
    return pending, len(targets)


_LINES = {
    TELEGRAM: texts.GATE_TELEGRAM_LINE,
    YOUTUBE: texts.GATE_YOUTUBE_LINE,
    TIKTOK: texts.GATE_TIKTOK_LINE,
}
_BUTTONS = {
    TELEGRAM: texts.GATE_JOIN_BUTTON,
    YOUTUBE: texts.GATE_YOUTUBE_BUTTON,
    TIKTOK: texts.GATE_TIKTOK_BUTTON,
}


def render_screen(pending: list[dict], total: int) -> tuple[str, InlineKeyboardMarkup]:
    done = total - len(pending)
    lines = [texts.GATE_TITLE.format(done=done, total=total), ""]
    rows = []
    for target in pending:
        name = target["display_name"]
        lines.append(_LINES[target["platform"]].format(name=texts.esc(name)))
        if target["url"]:
            rows.append(
                [
                    InlineKeyboardButton(
                        text=_BUTTONS[target["platform"]].format(name=name), url=target["url"]
                    )
                ]
            )
    text = "\n".join(lines)
    if any(target["platform"] in SOCIAL for target in pending):
        text += texts.GATE_SCREENSHOT_HELP
    text += texts.GATE_TAIL
    if any(target["platform"] == TELEGRAM for target in pending):
        rows.append(
            [InlineKeyboardButton(text=texts.GATE_CHECK_BUTTON, callback_data="gate:check")]
        )
    return text, InlineKeyboardMarkup(inline_keyboard=rows)
