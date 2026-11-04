"""/ban and /unban."""

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from bot import texts
from bot.app import App
from bot.db.roles import Role
from bot.filters import IsStaff

router = Router(name="moderation")


async def _resolve_target(message: Message, command: CommandObject, app: App) -> int | None:
    reply = message.reply_to_message
    if reply and reply.forward_origin and getattr(reply.forward_origin, "sender_user", None):
        return reply.forward_origin.sender_user.id
    argument = (command.args or "").strip()
    if not argument:
        return None
    if argument.lstrip("-").isdigit():
        return int(argument)
    return await app.users.find_id_by_username(argument)


@router.message(Command("ban"), IsStaff())
async def ban(message: Message, command: CommandObject, app: App, role: Role) -> None:
    has_target = command.args or message.reply_to_message
    if not has_target:
        await message.answer(texts.BAN_USAGE)
        return
    user_id = await _resolve_target(message, command, app)
    if user_id is None:
        await message.answer(texts.USER_NOT_FOUND)
        return
    target_role = await app.roles.resolve(user_id, None)
    if target_role == Role.OWNER:
        await message.answer(texts.CANT_BAN_OWNER)
        return
    if target_role == Role.MODERATOR:
        await message.answer(texts.CANT_BAN_STAFF)
        return
    if await app.users.is_banned(user_id):
        await message.answer(texts.ALREADY_BANNED.format(user_id=user_id))
        return
    await app.users.set_banned(user_id, True)
    await message.answer(texts.BANNED_OK.format(user_id=user_id))


@router.message(Command("unban"), IsStaff())
async def unban(message: Message, command: CommandObject, app: App) -> None:
    if not command.args and not message.reply_to_message:
        await message.answer(texts.UNBAN_USAGE)
        return
    user_id = await _resolve_target(message, command, app)
    if user_id is None:
        await message.answer(texts.USER_NOT_FOUND)
        return
    if not await app.users.is_banned(user_id):
        await message.answer(texts.NOT_BANNED.format(user_id=user_id))
        return
    await app.users.set_banned(user_id, False)
    await message.answer(texts.UNBANNED_OK.format(user_id=user_id))
