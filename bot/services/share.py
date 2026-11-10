"""Builds the links people share."""

from urllib.parse import quote

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot import texts
from bot.app import App
from bot.services.shortener import shorten

SHORT_LINK_TTL = 30 * 24 * 3600.0


async def plain_link(app: App, code: str) -> str:
    return f"https://t.me/{await app.bot_username()}?start={code}"


def share_button(link: str) -> InlineKeyboardButton:
    """One button that opens Telegram's forward dialog with this link filled in."""
    return InlineKeyboardButton(
        text=texts.BTN_SHARE_LINK, url=f"https://t.me/share/url?url={quote(link)}"
    )


def share_markup(link: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[share_button(link)]])


async def present_link(app: App, code: str) -> tuple[str, InlineKeyboardMarkup]:
    """The one way every finished link is shown: heading, link, share button."""
    link = await share_link(app, code)
    return texts.LINK_READY.format(link=link), share_markup(link)


async def share_link(app: App, code: str) -> str:
    """Shortened when the owner turned that on. If the shortener has a problem, the
    normal link is given and nobody needs to know."""
    link = await plain_link(app, code)
    config = await app.settings.get("shortener")
    if not config or not config.get("enabled"):
        return link
    cache_key = f"short:{config['site']}:{code}"
    found, value, fresh = await app.store.cache.get(cache_key)
    if found and fresh:
        return value
    short = await shorten(link, config["site"], config["key"])
    if not short:
        return link
    await app.store.cache.set(cache_key, short, SHORT_LINK_TTL)
    return short
