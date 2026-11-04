"""The force subscribe steps people go through: join buttons and screenshots."""

import logging

from aiogram import F, Router
from aiogram.dispatcher.event.bases import SkipHandler
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramNetworkError,
    TelegramServerError,
)
from aiogram.filters import StateFilter
from aiogram.types import CallbackQuery, ChatJoinRequest, Message

from bot import texts
from bot.app import App
from bot.db.targets import REVIEW_PENDING, SOCIAL, YOUTUBE
from bot.filters import IsInput
from bot.services import flow, gate, verification
from bot.services.verification import Verdict

log = logging.getLogger(__name__)
router = Router(name="force_sub")
MAX_DOWNLOAD_BYTES = 20 * 1024 * 1024  # What Telegram lets a bot download.


def _is_image_file(message: Message) -> bool:
    document = message.document
    return bool(document and (document.mime_type or "").startswith("image/"))


def _failure_text(verdict: Verdict, target: dict) -> str:
    name = texts.esc(target["display_name"])
    if verdict == Verdict.NOT_SUBSCRIBED:
        template = (
            texts.SCREENSHOT_NOT_SUBSCRIBED_YOUTUBE
            if target["platform"] == YOUTUBE
            else texts.SCREENSHOT_NOT_FOLLOWING_TIKTOK
        )
    else:
        template = texts.SCREENSHOT_UNCLEAR
    return template.format(name=name)


async def _download(message: Message) -> bytes | None:
    """None means the check can't run through no fault of theirs."""
    media = message.photo[-1] if message.photo else message.document
    try:
        downloaded = await message.bot.download(media)
        return downloaded.read()
    except (TelegramBadRequest, TelegramForbiddenError, TelegramNetworkError, TelegramServerError):
        log.warning("Could not fetch a screenshot; letting the person through", exc_info=True)
        return None


@router.message(F.photo | F.document, StateFilter(None))
async def picture(message: Message, app: App) -> None:
    if message.document and not _is_image_file(message):
        await _not_a_picture(message, app)
        return
    user_id = message.from_user.id
    code = await app.users.get_pending(user_id)
    if code is None:
        # The last pictures of an album may arrive after the files were delivered.
        if not message.media_group_id:
            await message.answer(texts.SCREENSHOT_NOT_NEEDED)
        return
    pending, total = await gate.pending_targets(app, user_id)
    social = [target for target in pending if target["platform"] in SOCIAL]
    if not pending:
        await flow.continue_flow(app, user_id)
        return
    if not social:
        await message.answer(texts.SCREENSHOT_JOIN_FIRST)
        return
    if message.document and (message.document.file_size or 0) > MAX_DOWNLOAD_BYTES:
        await message.answer(texts.SCREENSHOT_TOO_BIG)
        return

    progress = await message.answer(texts.SCREENSHOT_CHECKING)
    data = await _download(message)
    if data is None:
        check = verification.Check(target=social[0], verdict=Verdict.PASS)
    else:
        check = await verification.check_screenshot(data, social)

    if check.verdict != Verdict.PASS:
        attempts = await app.targets.record_failure(user_id, check.target)
        limit = app.config.screenshot_max_attempts
        if not limit or attempts < limit:
            await progress.edit_text(_failure_text(check.verdict, check.target))
            return
        log.info("User %s let through after %s attempts", user_id, attempts)
        # They get their files now. Staff can review the screenshot and ban them after.
        review = REVIEW_PENDING if app.log.enabled else None
        await app.targets.mark_verified(user_id, check.target, "let_through", review=review)
        app.log.review(message, check.target, attempts)
    else:
        await app.targets.mark_verified(user_id, check.target, "screenshot")
    await progress.edit_text(texts.SCREENSHOT_OK)
    await flow.continue_flow(app, user_id)


async def _not_a_picture(message: Message, app: App) -> None:
    pending, _ = await gate.pending_targets(app, message.from_user.id)
    code = await app.users.get_pending(message.from_user.id)
    if code and any(target["platform"] in SOCIAL for target in pending):
        await message.answer(texts.SCREENSHOT_WRONG_TYPE)
        return
    await message.answer(texts.UNKNOWN_MESSAGE)


@router.message(F.video | F.sticker | F.animation | F.video_note, StateFilter(None))
async def wrong_media(message: Message, app: App) -> None:
    await _not_a_picture(message, app)


@router.message(StateFilter(None), IsInput())
async def anything_while_waiting(message: Message, app: App) -> None:
    """Someone part way through who sends text gets reminded what's left."""
    user_id = message.from_user.id
    if await app.users.get_pending(user_id) is None:
        raise SkipHandler
    pending, total = await gate.pending_targets(app, user_id)
    if not pending:
        await flow.continue_flow(app, user_id)
        return
    text, markup = gate.render_screen(pending, total)
    await message.answer(text, reply_markup=markup)


@router.callback_query(F.data == "gate:check")
async def check_joined(callback: CallbackQuery, app: App) -> None:
    user_id = callback.from_user.id
    code = await app.users.get_pending(user_id)
    if code is None:
        await callback.answer(texts.SCREENSHOT_NOT_NEEDED, show_alert=True)
        return
    pending, total = await gate.pending_targets(app, user_id)
    if any(target["platform"] not in SOCIAL for target in pending):
        await callback.answer(texts.GATE_NOT_YET, show_alert=True)
        return
    await callback.answer()
    if pending:
        text, markup = gate.render_screen(pending, total)
        try:
            await callback.message.edit_text(text, reply_markup=markup)
        except TelegramBadRequest:
            pass
        return
    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass
    await flow.continue_flow(app, user_id)


@router.chat_join_request()
async def join_request(request: ChatJoinRequest, app: App) -> None:
    """Channels with join approval: asking to join counts."""
    target = await app.targets.find_by_chat(request.chat.id)
    if target is None:
        return
    user_id = request.from_user.id
    await app.targets.mark_verified(user_id, target, "join_request")
    if await app.users.is_banned(user_id):
        return
    try:
        await flow.continue_flow(app, user_id)
    except TelegramForbiddenError:
        log.info("User %s can't be messaged yet", user_id)
