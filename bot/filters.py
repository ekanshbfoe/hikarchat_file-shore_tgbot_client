"""Permission checks. These run on every command, whatever the menu shows."""

from aiogram.filters import BaseFilter
from aiogram.types import TelegramObject

from bot.db.roles import Role


class IsStaff(BaseFilter):
    async def __call__(self, event: TelegramObject, role: Role = Role.USER) -> bool:
        return role in (Role.OWNER, Role.MODERATOR)


class IsOwner(BaseFilter):
    async def __call__(self, event: TelegramObject, role: Role = Role.USER) -> bool:
        return role == Role.OWNER
