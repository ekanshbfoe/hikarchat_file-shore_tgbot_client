"""/genlink, /universal_link and /cancel. Collecting messages is shared with /special_link."""

from dataclasses import asdict

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    ReplyKeyboardRemove,
)

from bot import texts
from bot.app import App
from bot.db.links import SPECIAL, StaleEditError
from bot.filters import IsInput, IsStaff
from bot.services import share, storing
from bot.services.activity_log import actor
from bot.services.storing import StorageBlockedError
from bot.states import Collect

router = Router(name="links")
MAX_ITEMS = 1000

COLLECT_BUTTONS = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(text=texts.BTN_DONE, callback_data="collect:done"),
            InlineKeyboardButton(text=texts.BTN_CANCEL, callback_data="cancel"),
        ]
    ]
)


async def start_collecting(message: Message, state: FSMContext, kind: str, **extra) -> None:
    await state.clear()
    await state.set_state(Collect.messages)
    reply = message.reply_to_message
    sources = [storing.describe(reply)] if reply and storing.is_copyable(reply) else []
    await state.update_data(kind=kind, sources=sources, **extra)
    if sources:
        await message.answer(
            texts.COLLECT_REPLIED.format(count=len(sources)), reply_markup=COLLECT_BUTTONS
        )
    else:
        await message.answer(texts.COLLECT_PROMPT, reply_markup=COLLECT_BUTTONS)


@router.message(Command("genlink"), IsStaff())
async def genlink(message: Message, state: FSMContext) -> None:
    await start_collecting(message, state, "genlink")


@router.message(Command("universal_link"), IsStaff())
async def universal_link(message: Message, state: FSMContext) -> None:
    await start_collecting(message, state, "universal")


@router.message(Command("cancel"))
async def cancel_command(message: Message, state: FSMContext) -> None:
    if await state.get_state() is None:
        await message.answer(texts.NOTHING_TO_CANCEL)
        return
    await state.clear()
    await message.answer(texts.CANCELLED, reply_markup=ReplyKeyboardRemove())


@router.callback_query(F.data == "cancel")
async def cancel_button(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer()
    await callback.message.answer(texts.CANCELLED)


@router.message(Collect.messages, IsStaff(), IsInput())
async def collect(message: Message, state: FSMContext) -> None:
    if message.text and message.text.startswith("/"):
        await message.answer(texts.COLLECT_COMMAND_HINT, reply_markup=COLLECT_BUTTONS)
        return
    if not storing.is_copyable(message):
        await message.answer(texts.COLLECT_UNSUPPORTED)
        return
    data = await state.get_data()
    sources = data["sources"]
    if len(sources) >= MAX_ITEMS:
        await message.answer(texts.COLLECT_LIMIT, reply_markup=COLLECT_BUTTONS)
        return
    same_album = bool(
        sources
        and message.media_group_id
        and sources[-1]["media_group_id"] == message.media_group_id
    )
    sources.append(storing.describe(message))
    await state.update_data(sources=sources)
    # One album arrives as many messages. Answer it once, not ten times.
    if not same_album:
        await message.answer(
            texts.COLLECT_COUNT.format(count=len(sources)), reply_markup=COLLECT_BUTTONS
        )


@router.callback_query(F.data == "collect:done", Collect.messages, IsStaff())
async def done(callback: CallbackQuery, state: FSMContext, app: App) -> None:
    data = await state.get_data()
    sources = data["sources"]
    if not sources:
        await callback.answer(texts.COLLECT_EMPTY, show_alert=True)
        return
    await callback.answer()
    progress = await callback.message.answer(texts.STORING)
    try:
        items = await storing.store_messages(app, callback.message.chat.id, sources)
    except StorageBlockedError:
        await progress.edit_text(texts.STORAGE_BLOCKED)
        return  # Keep the session: nothing is lost once the owner fixes the channel.
    if not items:
        await state.clear()
        await progress.edit_text(texts.STORE_NOTHING_SAVED)
        return
    await state.clear()

    if data.get("add_to"):
        link = await app.links.get(data["add_to"])
        if link is None:
            await progress.edit_text(texts.LINK_GONE)
            return
        merged = [*link["items"], *[asdict(item) for item in items]]
        try:
            await app.links.replace_items(link["code"], merged, link["version"])
        except StaleEditError:
            await progress.edit_text(texts.SPECIAL_STALE)
            return
        app.log.post(
            texts.LOG_LINK_EDITED.format(
                actor=actor(callback.from_user), link=await share.plain_link(app, link["code"])
            )
        )
        text, markup = await share.present_link(app, link["code"])
        await progress.edit_text(texts.SPECIAL_UPDATED + "\n\n" + text, reply_markup=markup)
        return

    title = data.get("title") if data["kind"] == SPECIAL else None
    code = await app.links.create(data["kind"], callback.from_user.id, items, title=title)
    app.log.post(
        texts.LOG_LINK_CREATED.format(
            actor=actor(callback.from_user),
            count=len(items),
            link=await share.plain_link(app, code),
        )
    )
    text, markup = await share.present_link(app, code)
    await progress.edit_text(text, reply_markup=markup)
