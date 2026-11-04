"""/shortener: shorten any link."""

from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot import texts
from bot.app import App
from bot.db.roles import Role
from bot.filters import IsInput, IsStaff
from bot.services.shortener import is_link, shorten
from bot.states import ShortenerFlow

router = Router(name="shortener")


@router.message(Command("shortener"), IsStaff())
async def shortener(message: Message, state: FSMContext, app: App, role: Role) -> None:
    await state.clear()
    config = await app.settings.get("shortener")
    if not config:
        await message.answer(
            texts.SHORTENER_NOT_SET_OWNER if role == Role.OWNER else texts.SHORTENER_NOT_SET_MOD
        )
        return
    await state.set_state(ShortenerFlow.url)
    await message.answer(texts.SHORTENER_PROMPT)


@router.message(ShortenerFlow.url, IsStaff(), IsInput())
async def shorten_url(message: Message, state: FSMContext, app: App) -> None:
    url = (message.text or "").strip()
    if not is_link(url):
        await message.answer(texts.SHORTENER_BAD_LINK)
        return
    await state.clear()
    config = await app.settings.get("shortener")
    short = await shorten(url, config["site"], config["key"]) if config else None
    if short:
        await message.answer(texts.SHORTENER_RESULT.format(link=texts.esc(short)))
    else:
        await message.answer(texts.SHORTENER_FAILED)
