"""/start, Help and About, and opening shared links."""

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot import texts
from bot.app import App
from bot.db.roles import Role
from bot.services import flow

router = Router(name="start")


async def _home_markup(app: App) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(text=texts.BTN_HELP, callback_data="home:help"),
            InlineKeyboardButton(text=texts.BTN_ABOUT, callback_data="home:about"),
        ]
    ]
    update_channel = await app.settings.get("update_channel")
    if update_channel:
        rows.append([InlineKeyboardButton(text=texts.BTN_UPDATE_CHANNEL, url=update_channel)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


BACK_HOME = InlineKeyboardMarkup(
    inline_keyboard=[[InlineKeyboardButton(text=texts.BTN_BACK, callback_data="home:back")]]
)


def _welcome(name: str | None) -> str:
    return texts.WELCOME.format(name=texts.esc(name or "there"))


@router.message(Command("start"))
async def start(
    message: Message, command: CommandObject, state: FSMContext, app: App, role: Role
) -> None:
    await state.clear()
    if command.args:
        await flow.open_link(app, message.from_user.id, command.args.strip(), role != Role.USER)
        return
    await message.answer(
        _welcome(message.from_user.first_name), reply_markup=await _home_markup(app)
    )


async def _edit(callback: CallbackQuery, text: str, markup: InlineKeyboardMarkup) -> None:
    try:
        await callback.message.edit_text(text, reply_markup=markup)
    except TelegramBadRequest:
        pass  # A double tap: the screen already shows this.
    await callback.answer()


@router.callback_query(F.data == "home:help")
async def show_help(callback: CallbackQuery, role: Role) -> None:
    text = texts.HELP_USER
    if role != Role.USER:
        text = texts.HELP_STAFF
        if role == Role.OWNER:
            text += texts.HELP_OWNER_EXTRA
    await _edit(callback, text, BACK_HOME)


@router.callback_query(F.data == "home:about")
async def show_about(callback: CallbackQuery) -> None:
    await _edit(callback, texts.ABOUT, BACK_HOME)


@router.callback_query(F.data == "home:back")
async def back_home(callback: CallbackQuery, app: App) -> None:
    await _edit(callback, _welcome(callback.from_user.first_name), await _home_markup(app))
