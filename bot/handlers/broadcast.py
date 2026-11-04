"""/broadcast: send a message to everyone, after a preview."""

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot import texts
from bot.app import App
from bot.db.jobs import CANCELLED, RUNNING
from bot.filters import IsInput, IsStaff
from bot.services import broadcast as service
from bot.services.activity_log import actor
from bot.services.storing import is_copyable
from bot.states import BroadcastFlow

router = Router(name="broadcast")


async def _preview(message: Message, source: Message, app: App) -> None:
    if not is_copyable(source):
        await message.answer(texts.BROADCAST_NOT_COPYABLE)
        return
    count = await app.users.count_reachable()
    await app.bot.copy_message(message.chat.id, source.chat.id, source.message_id)
    await message.answer(
        texts.BROADCAST_PREVIEW.format(count=count),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=texts.BROADCAST_SEND, callback_data=f"bc:go:{source.message_id}"
                    ),
                    InlineKeyboardButton(text=texts.BTN_CANCEL, callback_data="cancel"),
                ]
            ]
        ),
    )


@router.message(Command("broadcast"), IsStaff())
async def broadcast(message: Message, state: FSMContext, app: App) -> None:
    await state.clear()
    if message.reply_to_message:
        await _preview(message, message.reply_to_message, app)
        return
    await state.set_state(BroadcastFlow.message)
    await message.answer(texts.BROADCAST_PROMPT)


@router.message(BroadcastFlow.message, IsStaff(), IsInput())
async def got_message(message: Message, state: FSMContext, app: App) -> None:
    await state.clear()
    await _preview(message, message, app)


@router.callback_query(F.data.startswith("bc:go:"), IsStaff())
async def go(callback: CallbackQuery, app: App) -> None:
    if await app.jobs.running(service.KIND):
        await callback.answer(texts.BROADCAST_BUSY, show_alert=True)
        return
    await callback.answer()
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except TelegramBadRequest:
        pass
    progress = await callback.message.answer(texts.BROADCAST_PROGRESS.format(sent=0))
    job_id = await app.jobs.create(
        service.KIND,
        callback.from_user.id,
        {
            "chat_id": callback.message.chat.id,
            "message_id": int(callback.data.rsplit(":", 1)[1]),
            "progress_id": progress.message_id,
        },
    )
    app.log.post(texts.LOG_BROADCAST_STARTED.format(actor=actor(callback.from_user)))
    app.runner.start(job_id, service.KIND)


@router.callback_query(F.data.startswith("bc:stop:"), IsStaff())
async def stop(callback: CallbackQuery, app: App) -> None:
    job_id = int(callback.data.rsplit(":", 1)[1])
    job = await app.jobs.get(job_id)
    if job and job["status"] == RUNNING:
        await app.jobs.finish(job_id, CANCELLED)
    await callback.answer()
