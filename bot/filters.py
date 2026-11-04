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


KNOWN_COMMANDS = {
    "start",
    "genlink",
    "universal_link",
    "batch",
    "special_link",
    "shortener",
    "settings",
    "broadcast",
    "ban",
    "unban",
    "cancel",
}


class IsInput(BaseFilter):
    """For conversation steps. A real command is never taken as an answer: it falls
    through to its own handler, which ends the conversation cleanly."""

    async def __call__(self, event: TelegramObject) -> bool:
        text = getattr(event, "text", None)
        if not text or not text.startswith("/"):
            return True
        return text[1:].split(maxsplit=1)[0].split("@")[0].lower() not in KNOWN_COMMANDS
