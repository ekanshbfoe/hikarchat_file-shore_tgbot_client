"""Decides whether a screenshot shows someone subscribed. Fast and forgiving on purpose.

The owner accepted that fakes can pass. What matters is that a genuine person is never
held up or stuck, so it only fails on a clearly visible not-subscribed button, or when
nothing relevant can be read at all.
"""

import asyncio
import logging
import re
from dataclasses import dataclass
from enum import StrEnum

from rapidfuzz import fuzz

from bot.db.targets import TIKTOK, YOUTUBE
from bot.services import ocr

log = logging.getLogger(__name__)

TIME_LIMIT_SECONDS = 8.0
NAME_MATCH = 80
WORD_MATCH = 88
MIN_NAME_LENGTH_FOR_FUZZY = 4

_YOUTUBE_SUBSCRIBED_HINDI = ("सदस्यता ली", "सब्सक्राइब किया", "सब्सक्राइब्ड")
_YOUTUBE_SUBSCRIBE_HINDI = ("सदस्यता लें", "सदस्यता लेँ", "सब्सक्राइब करें")
_TIKTOK_FOLLOWED_HINDI = ("फ़ॉलो कर रहे", "फॉलो कर रहे", "मैसेज", "संदेश", "दोस्त")
_TIKTOK_FOLLOW_HINDI = ("फ़ॉलो करें", "फॉलो करें")


class Verdict(StrEnum):
    PASS = "pass"
    NOT_SUBSCRIBED = "not_subscribed"
    UNCLEAR = "unclear"


@dataclass
class Check:
    target: dict
    verdict: Verdict


def _words(text: str) -> list[str]:
    return re.findall(r"[^\W_]+", text.lower())


def _has_word_like(words: list[str], wanted: str, exclude: set[str] = frozenset()) -> bool:
    """Exact or nearly so, allowing for a misread letter or two."""
    return any(
        word not in exclude and fuzz.ratio(word, wanted) >= WORD_MATCH
        for word in words
        if abs(len(word) - len(wanted)) <= 2
    )


def _names_for(target: dict) -> list[str]:
    names = [target["display_name"]]
    identity = target.get("identity") or ""
    if identity.startswith("@"):
        names.append(identity[1:])
    return names


def mentions(text: str, target: dict) -> bool:
    lowered = text.lower()
    for name in _names_for(target):
        name = name.strip().lower()
        if not name:
            continue
        if name in lowered:
            return True
        if (
            len(name) >= MIN_NAME_LENGTH_FOR_FUZZY
            and fuzz.partial_ratio(name, lowered) >= NAME_MATCH
        ):
            return True
    return False


def _judge_youtube(text: str, words: list[str], named: bool) -> Verdict:
    # "subscribe" and "subscribers" are close in spelling but mean something else.
    subscribed = _has_word_like(words, "subscribed", exclude={"subscribe", "subscribers"}) or any(
        phrase in text for phrase in _YOUTUBE_SUBSCRIBED_HINDI
    )
    if subscribed:
        return Verdict.PASS
    if "subscribe" in words or any(phrase in text for phrase in _YOUTUBE_SUBSCRIBE_HINDI):
        return Verdict.NOT_SUBSCRIBED
    return Verdict.PASS if named else Verdict.UNCLEAR


def _judge_tiktok(text: str, words: list[str], named: bool) -> Verdict:
    # Every profile shows a "Following" count, so one "following" proves nothing.
    following_count = sum(1 for word in words if word == "following")
    followed = (
        following_count >= 2
        or _has_word_like(words, "message")
        or _has_word_like(words, "friends")
        or any(phrase in text for phrase in _TIKTOK_FOLLOWED_HINDI)
    )
    if followed:
        return Verdict.PASS
    if "follow" in words or any(phrase in text for phrase in _TIKTOK_FOLLOW_HINDI):
        return Verdict.NOT_SUBSCRIBED
    return Verdict.PASS if named else Verdict.UNCLEAR


def judge(text: str, target: dict) -> Verdict:
    named = mentions(text, target)
    words = _words(text)
    if target["platform"] == YOUTUBE:
        return _judge_youtube(text, words, named)
    if target["platform"] == TIKTOK:
        return _judge_tiktok(text, words, named)
    raise ValueError(target["platform"])


def choose_target(text: str, pending: list[dict]) -> dict:
    """Screenshots can come in any order: credit the channel they name, otherwise a
    channel on the platform they look like, otherwise the next one waiting."""
    for target in pending:
        if mentions(text, target):
            return target
    words = _words(text)
    looks_like = TIKTOK if "tiktok" in words or "followers" in words else None
    if "subscribers" in words or "subscribed" in words or "youtube" in words:
        looks_like = YOUTUBE
    for target in pending:
        if target["platform"] == looks_like:
            return target
    return pending[0]


async def _read(main: bytes, other: bytes, pending: list[dict]) -> Check:
    """Read in English, then Hindi, trying both polarities. Text is merged, so the page
    can come from one polarity and the button from the other."""
    text = ""
    for language in (ocr.ENGLISH, ocr.HINDI):
        for image in (main, other):
            text += "\n" + await ocr.read_text(image, language)
            target = choose_target(text, pending)
            verdict = judge(text, target)
            if verdict != Verdict.UNCLEAR:
                return Check(target=target, verdict=verdict)
    return Check(target=pending[0], verdict=Verdict.UNCLEAR)


async def check_screenshot(data: bytes, pending: list[dict]) -> Check:
    """Never raises for anything on our side: if the check itself can't run, the person
    passes rather than being blocked by our fault."""
    try:
        main, other = await asyncio.to_thread(ocr.prepare_image, data)
    except ocr.NotAnImageError:
        return Check(target=pending[0], verdict=Verdict.UNCLEAR)
    except Exception:
        log.exception("Could not prepare a screenshot; letting the person through")
        return Check(target=pending[0], verdict=Verdict.PASS)
    try:
        async with asyncio.timeout(TIME_LIMIT_SECONDS):
            return await _read(main, other, pending)
    except TimeoutError:
        log.warning("Screenshot check hit the time limit; letting the person through")
    except Exception:
        log.exception("Screenshot check failed; letting the person through")
    return Check(target=pending[0], verdict=Verdict.PASS)
