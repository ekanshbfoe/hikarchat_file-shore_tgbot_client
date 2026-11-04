"""Understands the YouTube and TikTok links the owner pastes."""

import logging
import re
from dataclasses import dataclass
from urllib.parse import urlsplit

import aiohttp

from bot.db.targets import TIKTOK, YOUTUBE

log = logging.getLogger(__name__)
REDIRECT_TIMEOUT_SECONDS = 8

_YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"}
_YOUTUBE_VIDEO_PATHS = ("watch", "shorts", "live", "playlist", "embed", "v", "results", "feed")
_TIKTOK_HOSTS = {"tiktok.com", "www.tiktok.com", "m.tiktok.com"}
_TIKTOK_SHORT_HOSTS = {"vm.tiktok.com", "vt.tiktok.com"}
_HANDLE = re.compile(r"^@[\w.\-]{1,100}$")


@dataclass
class Parsed:
    identity: str
    url: str


class VideoLinkError(ValueError):
    """A link to one video rather than to the channel."""


def _split(text: str):
    text = text.strip()
    if "://" not in text:
        text = f"https://{text}"
    parts = urlsplit(text)
    segments = [segment for segment in parts.path.split("/") if segment]
    return (parts.hostname or "").lower(), segments


def parse_youtube(text: str) -> Parsed | None:
    """Raises VideoLinkError for a video link. Returns None if it can't be read."""
    text = text.strip()
    if _HANDLE.match(text):
        handle = text.lower()
        return Parsed(handle, f"https://www.youtube.com/{handle}")
    host, segments = _split(text)
    if host == "youtu.be":
        raise VideoLinkError
    if host not in _YOUTUBE_HOSTS or not segments:
        return None
    first = segments[0]
    if first.startswith("@") and _HANDLE.match(first):
        handle = first.lower()
        return Parsed(handle, f"https://www.youtube.com/{handle}")
    if first in _YOUTUBE_VIDEO_PATHS:
        raise VideoLinkError
    if len(segments) >= 2 and first == "channel":
        # Channel ids are case sensitive.
        return Parsed(f"channel:{segments[1]}", f"https://www.youtube.com/channel/{segments[1]}")
    if len(segments) >= 2 and first in ("c", "user"):
        name = segments[1]
        return Parsed(f"{first}:{name.lower()}", f"https://www.youtube.com/{first}/{name}")
    return None


def _parse_tiktok_path(segments: list[str]) -> Parsed | None:
    if segments and segments[0].startswith("@") and _HANDLE.match(segments[0]):
        handle = segments[0].lower()
        return Parsed(handle, f"https://www.tiktok.com/{handle}")
    return None


async def _follow_redirect(url: str) -> str | None:
    try:
        timeout = aiohttp.ClientTimeout(total=REDIRECT_TIMEOUT_SECONDS)
        async with (
            aiohttp.ClientSession(timeout=timeout) as session,
            session.get(url, allow_redirects=True) as response,
        ):
            return str(response.url)
    except Exception:
        log.info("Could not follow a short TikTok link", exc_info=True)
        return None


async def parse_tiktok(text: str) -> Parsed | None:
    text = text.strip()
    if _HANDLE.match(text):
        handle = text.lower()
        return Parsed(handle, f"https://www.tiktok.com/{handle}")
    host, segments = _split(text)
    is_short = host in _TIKTOK_SHORT_HOSTS or (host in _TIKTOK_HOSTS and segments[:1] == ["t"])
    if is_short:
        address = text if "://" in text else f"https://{text}"
        resolved = await _follow_redirect(address)
        if not resolved:
            return None
        host, segments = _split(resolved)
    if host not in _TIKTOK_HOSTS:
        return None
    return _parse_tiktok_path(segments)


async def parse_social(platform: str, text: str) -> Parsed | None:
    if platform == YOUTUBE:
        return parse_youtube(text)
    if platform == TIKTOK:
        return await parse_tiktok(text)
    raise ValueError(platform)
