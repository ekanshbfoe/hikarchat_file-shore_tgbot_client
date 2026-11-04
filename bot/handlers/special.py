"""/special_link: multi-message links that can be changed later, keeping the same link."""

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot import texts
from bot.app import App
from bot.db.links import SPECIAL, StaleEditError
from bot.filters import IsInput, IsStaff
from bot.handlers.links import start_collecting
from bot.services import share
from bot.services.activity_log import actor
from bot.states import Special

router = Router(name="special")
MAX_NAME = 60
ITEM_LABEL = 28


def _button(text: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=data)


async def _menu(app: App) -> tuple[str, InlineKeyboardMarkup]:
    rows = [[_button(texts.SPECIAL_NEW, "sp:new")]]
    for link in await app.links.list_special():
        title = link["title"] or texts.SPECIAL_UNTITLED
        rows.append([_button(f"{title} ({link['items']})", f"sp:open:{link['code']}")])
    return texts.SPECIAL_MENU, InlineKeyboardMarkup(inline_keyboard=rows)


async def _link_view(app: App, link: dict) -> tuple[str, InlineKeyboardMarkup]:
    code = link["code"]
    text = texts.SPECIAL_VIEW.format(
        title=texts.esc(link["title"] or texts.SPECIAL_UNTITLED),
        count=len(link["items"]),
        link=await share.share_link(app, code),
    )
    markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [_button(texts.SPECIAL_ADD, f"sp:add:{code}")],
            [_button(texts.SPECIAL_ITEMS, f"sp:items:{code}")],
            [_button(texts.SPECIAL_DELETE, f"sp:del:{code}")],
            [_button(texts.BTN_BACK, "sp:menu")],
        ]
    )
    return text, markup


def _items_view(link: dict) -> tuple[str, InlineKeyboardMarkup]:
    code, version = link["code"], link["version"]
    rows = []
    for position, item in enumerate(link["items"]):
        label = item.get("file_name") or texts.SPECIAL_ITEM_FALLBACK.format(number=position + 1)
        rows.append(
            [
                _button(label[:ITEM_LABEL], f"sp:noop:{code}"),
                _button("⬆️", f"sp:up:{code}:{position}:{version}"),
                _button("⬇️", f"sp:dn:{code}:{position}:{version}"),
                _button("🗑", f"sp:rm:{code}:{position}:{version}"),
            ]
        )
    rows.append([_button(texts.BTN_BACK, f"sp:open:{code}")])
    text = texts.SPECIAL_ITEMS_TITLE if link["items"] else texts.SPECIAL_NO_ITEMS
    return text, InlineKeyboardMarkup(inline_keyboard=rows)


async def _show(callback: CallbackQuery, text: str, markup: InlineKeyboardMarkup) -> None:
    try:
        await callback.message.edit_text(text, reply_markup=markup)
    except TelegramBadRequest:
        pass  # Double tap: the screen already shows this.


@router.message(Command("special_link"), IsStaff())
async def special_link(message: Message, state: FSMContext, app: App) -> None:
    await state.clear()
    text, markup = await _menu(app)
    await message.answer(text, reply_markup=markup)


@router.callback_query(F.data == "sp:menu", IsStaff())
async def menu(callback: CallbackQuery, app: App) -> None:
    text, markup = await _menu(app)
    await _show(callback, text, markup)
    await callback.answer()


@router.callback_query(F.data == "sp:new", IsStaff())
async def new(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(Special.name)
    await callback.answer()
    await callback.message.answer(texts.SPECIAL_NAME_PROMPT)


@router.message(Special.name, IsStaff(), IsInput())
async def name(message: Message, state: FSMContext) -> None:
    title = (message.text or "").strip()
    if not title or title.startswith("/") or len(title) > MAX_NAME:
        await message.answer(texts.SPECIAL_NAME_INVALID)
        return
    await start_collecting(message, state, SPECIAL, title=title)


async def _load(callback: CallbackQuery, app: App, code: str) -> dict | None:
    link = await app.links.get(code)
    if link is None or link["kind"] != SPECIAL:
        await callback.answer(texts.LINK_GONE, show_alert=True)
        return None
    return link


@router.callback_query(F.data.startswith("sp:open:"), IsStaff())
async def open_link(callback: CallbackQuery, app: App) -> None:
    link = await _load(callback, app, callback.data.split(":")[2])
    if link:
        text, markup = await _link_view(app, link)
        await _show(callback, text, markup)
        await callback.answer()


@router.callback_query(F.data.startswith("sp:add:"), IsStaff())
async def add(callback: CallbackQuery, state: FSMContext, app: App) -> None:
    link = await _load(callback, app, callback.data.split(":")[2])
    if link:
        await callback.answer()
        await start_collecting(callback.message, state, SPECIAL, add_to=link["code"])


@router.callback_query(F.data.startswith("sp:items:"), IsStaff())
async def items(callback: CallbackQuery, app: App) -> None:
    link = await _load(callback, app, callback.data.split(":")[2])
    if link:
        text, markup = _items_view(link)
        await _show(callback, text, markup)
        await callback.answer()


@router.callback_query(F.data.startswith("sp:noop:"), IsStaff())
async def noop(callback: CallbackQuery) -> None:
    await callback.answer()


def _rearranged(items_now: list[dict], action: str, position: int) -> list[dict] | None:
    result = list(items_now)
    if not 0 <= position < len(result):
        return None
    if action == "rm":
        del result[position]
        return result
    other = position - 1 if action == "up" else position + 1
    if not 0 <= other < len(result):
        return None  # Already at the top or bottom.
    result[position], result[other] = result[other], result[position]
    return result


@router.callback_query(F.data.regexp(r"^sp:(up|dn|rm):"), IsStaff())
async def change_item(callback: CallbackQuery, app: App) -> None:
    _, action, code, position, version = callback.data.split(":")
    link = await _load(callback, app, code)
    if link is None:
        return
    if link["version"] != int(version):
        text, markup = _items_view(link)
        await _show(callback, text, markup)
        await callback.answer(texts.SPECIAL_STALE, show_alert=True)
        return
    rearranged = _rearranged(link["items"], action, int(position))
    if rearranged is None:
        await callback.answer()
        return
    try:
        await app.links.replace_items(code, rearranged, link["version"])
    except StaleEditError:
        await callback.answer(texts.SPECIAL_STALE, show_alert=True)
    else:
        await callback.answer(texts.SPECIAL_UPDATED)
        app.log.post(
            texts.LOG_LINK_EDITED.format(
                actor=actor(callback.from_user), link=await share.plain_link(app, code)
            )
        )
    link = await _load(callback, app, code)
    if link:
        text, markup = _items_view(link)
        await _show(callback, text, markup)


@router.callback_query(F.data.startswith("sp:del:"), IsStaff())
async def confirm_delete(callback: CallbackQuery, app: App) -> None:
    link = await _load(callback, app, callback.data.split(":")[2])
    if link:
        text = texts.SPECIAL_DELETE_CONFIRM.format(
            title=texts.esc(link["title"] or texts.SPECIAL_UNTITLED)
        )
        markup = InlineKeyboardMarkup(
            inline_keyboard=[
                [_button(texts.SPECIAL_DELETE_YES, f"sp:delyes:{link['code']}")],
                [_button(texts.BTN_BACK, f"sp:open:{link['code']}")],
            ]
        )
        await _show(callback, text, markup)
        await callback.answer()


@router.callback_query(F.data.startswith("sp:delyes:"), IsStaff())
async def delete(callback: CallbackQuery, app: App) -> None:
    link = await _load(callback, app, callback.data.split(":")[2])
    if link:
        await app.links.delete(link["code"])
        app.log.post(
            texts.LOG_LINK_DELETED.format(
                actor=actor(callback.from_user),
                title=texts.esc(link["title"] or texts.SPECIAL_UNTITLED),
            )
        )
        await callback.answer(texts.SPECIAL_DELETED)
        text, markup = await _menu(app)
        await _show(callback, text, markup)
