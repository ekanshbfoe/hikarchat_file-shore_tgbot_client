"""/batch: store a range of posts from a channel."""

from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot import texts
from bot.app import App
from bot.filters import IsInput, IsStaff
from bot.services import batch as batch_service
from bot.services.activity_log import actor
from bot.states import Batch

router = Router(name="batch")


@router.message(Command("batch"), IsStaff())
async def batch(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(Batch.first)
    await message.answer(texts.BATCH_FIRST)


@router.message(Batch.first, IsStaff(), IsInput())
async def first_post(message: Message, state: FSMContext, app: App) -> None:
    post = await batch_service.parse_post(app, message)
    if post is None:
        await message.answer(texts.BATCH_NOT_A_POST)
        return
    problem = await batch_service.check_source(app, post[0])
    if problem:
        await state.clear()
        await message.answer(problem)
        return
    await state.update_data(channel=post[0], first=post[1])
    await state.set_state(Batch.last)
    await message.answer(texts.BATCH_LAST)


@router.message(Batch.last, IsStaff(), IsInput())
async def last_post(message: Message, state: FSMContext, app: App) -> None:
    post = await batch_service.parse_post(app, message)
    if post is None:
        await message.answer(texts.BATCH_NOT_A_POST)
        return
    data = await state.get_data()
    if post[0] != data["channel"]:
        await message.answer(texts.BATCH_DIFFERENT_CHANNEL)
        return
    first, last = sorted((data["first"], post[1]))  # Reverse order is fine.
    count = last - first + 1
    if count > batch_service.MAX_POSTS:
        await message.answer(
            texts.BATCH_TOO_MANY.format(count=count, limit=batch_service.MAX_POSTS)
        )
        return
    await state.clear()

    code = await app.links.create("batch", message.from_user.id, [])
    progress = await message.answer(texts.BATCH_PROGRESS.format(done=0, total=count))
    job_id = await app.jobs.create(
        batch_service.KIND,
        message.from_user.id,
        {
            "source": post[0],
            "first": first,
            "last": last,
            "code": code,
            "chat_id": message.chat.id,
            "progress_id": progress.message_id,
            "actor": actor(message.from_user),
        },
    )
    app.runner.start(job_id, batch_service.KIND)
