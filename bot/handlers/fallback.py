"""Whatever nothing else handled. Registered last."""

from aiogram import Router
from aiogram.types import CallbackQuery, Message

from bot import texts

router = Router(name="fallback")


@router.callback_query()
async def old_button(callback: CallbackQuery) -> None:
    await callback.answer(texts.BUTTON_EXPIRED)


@router.message()
async def anything_else(message: Message) -> None:
    await message.answer(texts.UNKNOWN_MESSAGE)
