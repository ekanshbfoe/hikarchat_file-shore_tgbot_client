"""Builds the links people share."""

from bot.app import App


async def plain_link(app: App, code: str) -> str:
    return f"https://t.me/{await app.bot_username()}?start={code}"


async def share_link(app: App, code: str) -> str:
    return await plain_link(app, code)
