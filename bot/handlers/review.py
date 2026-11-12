"""The Approve / Not Approve buttons in the logs group."""

import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import CallbackQuery, Message

from bot import texts
from bot.app import App
from bot.db.roles import Role
from bot.filters import IsStaff
from bot.services.activity_log import actor

log = logging.getLogger(__name__)
router = Router(name="review")


async def _show_outcome(callback: CallbackQuery, line: str | None) -> None:
    """Record the decision on the message and take the buttons away."""
    message = callback.message
    if not isinstance(message, Message):
        return  # Too old for Telegram to show us. The decision still counted.
    try:
        if line is None:
            await message.edit_reply_markup(reply_markup=None)
            return
        updated = f"{message.html_text}\n\n{line}"
        if message.text:
            await message.edit_text(updated, reply_markup=None)
        else:
            await message.edit_caption(caption=updated, reply_markup=None)
    except (TelegramBadRequest, TelegramForbiddenError):
        log.info("Could not update a review message", exc_info=True)


@router.callback_query(F.data.regexp(r"^rv:(ok|no):\d+:\d+$"), IsStaff())
async def decide(callback: CallbackQuery, app: App) -> None:
    _, action, user_id, target_id = callback.data.split(":")
    user_id, target_id = int(user_id), int(target_id)
    approved = action == "ok"
    if not approved and await app.roles.resolve(user_id, None) != Role.USER:
        await callback.answer(texts.REVIEW_IS_STAFF, show_alert=True)
        return
    if not await app.targets.decide_review(user_id, target_id, approved):
        await callback.answer(texts.REVIEW_ALREADY_DECIDED, show_alert=True)
        await _show_outcome(callback, None)
        return
    if approved:
        await app.audit.record(callback.from_user.id, "review_approved", user=user_id)
        line = texts.REVIEW_APPROVED_BY.format(actor=actor(callback.from_user))
    else:
        await app.audit.record(callback.from_user.id, "review_rejected", user=user_id)
        await app.users.set_banned(user_id, True)
        # Nothing should arrive automatically if they're ever unbanned.
        await app.users.set_pending(user_id, None)
        line = texts.REVIEW_REJECTED_BY.format(actor=actor(callback.from_user))
    await callback.answer()
    await _show_outcome(callback, line)


@router.callback_query(F.data.startswith("rv:"))
async def not_allowed(callback: CallbackQuery) -> None:
    await callback.answer(texts.REVIEW_STAFF_ONLY, show_alert=True)
