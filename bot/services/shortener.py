"""Shortens links using the provider the owner set up. A failure is never shown to anyone
as a failure: callers fall back to the normal link."""

import json
import logging
import re
from urllib.parse import urlsplit

import aiohttp

log = logging.getLogger(__name__)
TIMEOUT_SECONDS = 10
_SITE = re.compile(r"^(?=.{4,253}$)([a-z0-9-]+\.)+[a-z]{2,}(?::\d+)?$")


def clean_site(text: str) -> str | None:
    site = text.strip().lower()
    site = re.sub(r"^https?://", "", site).split("/")[0]
    return site if _SITE.match(site) else None


def is_link(text: str) -> bool:
    parts = urlsplit(text.strip())
    return parts.scheme in ("http", "https") and "." in parts.netloc and " " not in text.strip()


def _read_result(body: str) -> str | None:
    """Providers answer in JSON ({"status": "success", "shortenedUrl": ...}) or plain text."""
    try:
        data = json.loads(body)
    except ValueError:
        text = body.strip()
        return text if is_link(text) else None
    if not isinstance(data, dict):
        return None
    if str(data.get("status", "")).lower() == "error":
        return None
    for key in ("shortenedUrl", "shortened_url", "short_url", "shortlink", "result_url", "url"):
        value = data.get(key)
        if isinstance(value, str) and is_link(value):
            return value
    return None


async def shorten(url: str, site: str, key: str) -> str | None:
    try:
        timeout = aiohttp.ClientTimeout(total=TIMEOUT_SECONDS)
        async with (
            aiohttp.ClientSession(timeout=timeout) as session,
            session.get(f"https://{site}/api", params={"api": key, "url": url}) as response,
        ):
            if response.status != 200:
                log.info("Shortener answered %s", response.status)
                return None
            return _read_result(await response.text())
    except Exception:
        log.info("Shortener unavailable", exc_info=True)
        return None
