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
_TIKTOK_FOLLOWED_HINDI = ("फ़ॉलो कर रहे", "फॉलो कर रहे")
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


def _is_word_like(word: str, wanted: str) -> bool:
    """Nearly so, allowing for a misread letter or two."""
    return abs(len(word) - len(wanted)) <= 2 and fuzz.ratio(word, wanted) >= WORD_MATCH


def _word_means(word: str, wanted: str, others: tuple) -> bool:
    """The word looks like `wanted`, and looks more like it than like any `others`.
    Subscribe/subscribed/subscribers differ by one letter but mean different things,
    so a misread must be judged by its nearest spelling. Equally close means unclear."""
    if not _is_word_like(word, wanted):
        return False
    return all(fuzz.ratio(word, other) < fuzz.ratio(word, wanted) for other in others)


def _has_word_like(
    words: list[str], wanted: str, exclude: set[str] = frozenset(), unless: tuple = ()
) -> bool:
    """Exact or nearly so. A word that itself looks like one of `unless` doesn't count:
    "subscribers" must not be mistaken for "subscribe", and the other way round."""
    return any(
        word not in exclude
        and _is_word_like(word, wanted)
        and not any(_is_word_like(word, other) for other in unless)
        for word in words
        if abs(len(word) - len(wanted)) <= 2
    )


def _means_one_of(words: list[str], wanted: str, others: tuple) -> bool:
    return any(_word_means(word, wanted, others) for word in words)


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


def _judge_youtube(text: str, words: list[str]) -> Verdict:
    # "subscribe" and "subscribers" are close in spelling but mean something else, so
    # a misread counts only when its nearest spelling settles it. The not-subscribed
    # check runs first: anything ambiguous asks again rather than passing.
    not_subscribed = _means_one_of(
        words, "subscribe", ("subscribed", "subscribers")
    ) or any(phrase in text for phrase in _YOUTUBE_SUBSCRIBE_HINDI)
    if not_subscribed:
        return Verdict.NOT_SUBSCRIBED
    subscribed = _means_one_of(
        words, "subscribed", ("subscribe", "subscribers")
    ) or any(phrase in text for phrase in _YOUTUBE_SUBSCRIBED_HINDI)
    if subscribed:
        return Verdict.PASS
    return Verdict.UNCLEAR


def _tiktok_not_following(readings: list[str]) -> bool:
    for text in readings:
        words = _words(text)
        if _means_one_of(words, "follow", ("following", "followers")) or any(
            phrase in text for phrase in _TIKTOK_FOLLOW_HINDI
        ):
            return True
    return False


def _tiktok_followed(readings: list[str]) -> bool:
    """Within one reading only: the profile's own "Following" count, plus a second
    "following" — the button. The Message button proves nothing: creator pages show
    it to people who don't follow. And the same word seen twice only because two
    readings scanned the same page must not be mistaken for the button."""
    for text in readings:
        words = _words(text)
        following_count = sum(1 for word in words if word == "following")
        if (
            following_count >= 2
            or _has_word_like(words, "friends")
            or any(phrase in text for phrase in _TIKTOK_FOLLOWED_HINDI)
        ):
            return True
    return False


def judge_readings(readings: list[str], target: dict) -> Verdict:
    """The channel's own page must be visible before any button counts: a Subscribed
    button on some other channel's page proves nothing about this one. TikTok signals
    are judged reading by reading, never on the pile of words as a whole."""
    if not mentions("\n".join(readings), target):
        return Verdict.UNCLEAR
    if target["platform"] == YOUTUBE:
        text = "\n".join(readings)
        return _judge_youtube(text, _words(text))
    if target["platform"] == TIKTOK:
        if _tiktok_not_following(readings):
            return Verdict.NOT_SUBSCRIBED
        if _tiktok_followed(readings):
            return Verdict.PASS
        return Verdict.UNCLEAR
    raise ValueError(target["platform"])


def judge(text: str, target: dict) -> Verdict:
    return judge_readings([text], target)


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
    """Read in English, then Hindi, trying both polarities. Readings are kept apart,
    so a word repeated across readings cannot be mistaken for two words on the page."""
    readings: list[str] = []
    for language in (ocr.ENGLISH, ocr.HINDI):
        for image in (main, other):
            readings.append(await ocr.read_text(image, language))
            target = choose_target("\n".join(readings), pending)
            verdict = judge_readings(readings, target)
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
