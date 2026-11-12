"""Uses the real OCR engine on drawn screenshots."""

import shutil
import time

import pytest

from bot.db.targets import TIKTOK, YOUTUBE
from bot.services import ocr, verification
from bot.services.verification import Verdict, check_screenshot, choose_target, judge
from tests import screenshots

pytestmark = pytest.mark.skipif(shutil.which("tesseract") is None, reason="needs tesseract")

YT = {
    "id": 1,
    "platform": YOUTUBE,
    "display_name": "Cool Edits",
    "identity": "@cooledits",
    "version": 1,
}
TT = {
    "id": 2,
    "platform": TIKTOK,
    "display_name": "Cool Edits",
    "identity": "@cooledits",
    "version": 1,
}


@pytest.mark.parametrize("dark", [False, True])
async def test_youtube_subscribed_passes(dark):
    check = await check_screenshot(screenshots.youtube(dark=dark), [YT])
    assert check.verdict == Verdict.PASS


@pytest.mark.parametrize("dark", [False, True])
async def test_youtube_not_subscribed_fails(dark):
    check = await check_screenshot(screenshots.youtube(subscribed=False, dark=dark), [YT])
    assert check.verdict == Verdict.NOT_SUBSCRIBED


@pytest.mark.parametrize("state", ["following", "friends"])
async def test_tiktok_followed_passes(state):
    check = await check_screenshot(screenshots.tiktok(state=state), [TT])
    assert check.verdict == Verdict.PASS


async def test_tiktok_not_following_fails_despite_the_following_count():
    check = await check_screenshot(screenshots.tiktok(state="not"), [TT])
    assert check.verdict == Verdict.NOT_SUBSCRIBED


@pytest.mark.parametrize("dark", [False, True])
async def test_other_channels_subscribed_page_does_not_pass(dark):
    # The button says Subscribed, but the page is another channel: no name, no pass.
    check = await check_screenshot(
        screenshots.youtube(name="Other Studio", handle="@otherstudio", dark=dark), [YT]
    )
    assert check.verdict == Verdict.UNCLEAR


async def test_other_tiktok_profile_does_not_pass():
    check = await check_screenshot(
        screenshots.tiktok(name="Other Studio", handle="@otherstudio", state="following"), [TT]
    )
    assert check.verdict == Verdict.UNCLEAR


async def test_missing_clock_is_not_a_problem():
    check = await check_screenshot(screenshots.youtube(clock=False), [YT])
    assert check.verdict == Verdict.PASS


async def test_unrelated_picture_is_unclear():
    check = await check_screenshot(screenshots.unrelated(), [YT])
    assert check.verdict == Verdict.UNCLEAR


async def test_blank_picture_is_unclear():
    check = await check_screenshot(screenshots.blank(), [YT])
    assert check.verdict == Verdict.UNCLEAR


async def test_not_a_picture_is_unclear_not_a_crash():
    check = await check_screenshot(b"this is not an image", [YT])
    assert check.verdict == Verdict.UNCLEAR


async def test_check_is_fast():
    # Hindi fallback included: the slowest path is a picture with nothing relevant.
    started = time.monotonic()
    await check_screenshot(screenshots.unrelated(), [YT])
    assert time.monotonic() - started < verification.TIME_LIMIT_SECONDS


async def test_time_limit_lets_person_through_and_stops_the_program(monkeypatch):
    monkeypatch.setattr(verification, "TIME_LIMIT_SECONDS", 0.001)
    check = await check_screenshot(screenshots.youtube(subscribed=False), [YT])
    assert check.verdict == Verdict.PASS


async def test_broken_engine_lets_person_through(monkeypatch):
    async def broken(image, language):
        raise RuntimeError("engine missing")

    monkeypatch.setattr(ocr, "read_text", broken)
    check = await check_screenshot(screenshots.youtube(subscribed=False), [YT])
    assert check.verdict == Verdict.PASS


async def test_hindi_only_runs_when_english_finds_nothing(monkeypatch):
    languages = []
    real = ocr.read_text

    async def spy(image, language):
        languages.append(language)
        return await real(image, language)

    monkeypatch.setattr(ocr, "read_text", spy)
    await check_screenshot(screenshots.youtube(), [YT])
    assert languages == [ocr.ENGLISH]
    languages.clear()
    await check_screenshot(screenshots.unrelated(), [YT])
    # Both polarities in English, then both in Hindi.
    assert languages == [ocr.ENGLISH, ocr.ENGLISH, ocr.HINDI, ocr.HINDI]


# --- Decision rules on text, including misreads ---


@pytest.mark.parametrize(
    ("text", "verdict"),
    [
        ("Cool Edits 1M subscribers Subscribed", Verdict.PASS),
        ("Cool Edits 1M subscribers Subscrbed", Verdict.PASS),
        ("Cool Edits 1M subscribers Subscribe", Verdict.NOT_SUBSCRIBED),
        ("@cooledits Subscribed", Verdict.PASS),  # The handle names the page too.
        ("1M subscribers Subscribe", Verdict.UNCLEAR),  # No name: not this page.
        ("Subscribed", Verdict.UNCLEAR),  # Button alone names nobody.
        ("Anupam Music 217K subscribers Subscribed", Verdict.UNCLEAR),  # Other channel.
        ("Cool Edits 1M subscribers Subscribes", Verdict.UNCLEAR),  # Nearest the count word.
        ("Cool Edits 1M subscribers Subscrlbe", Verdict.NOT_SUBSCRIBED),  # Nearest Subscribe.
        ("Cool Edits 1M subscribers", Verdict.UNCLEAR),  # Name readable, button not.
        ("Coo1 Ed1ts videos", Verdict.UNCLEAR),  # Name misread a little.
        ("sunny and warm", Verdict.UNCLEAR),
        ("", Verdict.UNCLEAR),
        ("Cool Edits सदस्यता ली गई", Verdict.PASS),
        ("Cool Edits सदस्यता लें", Verdict.NOT_SUBSCRIBED),
    ],
)
def test_youtube_rules(text, verdict):
    assert judge(text, YT) == verdict


@pytest.mark.parametrize(
    ("text", "verdict"),
    [
        ("@cooledits 12 Following 4 Followers 1 Likes Message", Verdict.PASS),
        ("@cooledits 12 Following 4 Followers 1 Likes Friends", Verdict.PASS),
        ("@cooledits 12 Following 4 Followers Following", Verdict.PASS),
        ("@cooledits 12 Following 4 Followers 1 Likes Follow", Verdict.NOT_SUBSCRIBED),
        ("Cool Edits 12 Following Message", Verdict.PASS),  # Name names the page too.
        ("12 Following 4 Followers Message", Verdict.UNCLEAR),  # No name: not this page.
        ("12 Following 4 Followers Folliow", Verdict.UNCLEAR),  # No name.
        ("Other Studio 12 Following 4 Followers Message", Verdict.UNCLEAR),  # Other profile.
        ("12 Following 4 Followers Foloow", Verdict.UNCLEAR),  # Too garbled to call: ask.
        ("@cooledits 12 Following 4 Followers", Verdict.UNCLEAR),  # Button not readable.
        ("12 Following 4 Followers", Verdict.UNCLEAR),
        ("nothing useful", Verdict.UNCLEAR),
        ("Cool Edits फ़ॉलो करें", Verdict.NOT_SUBSCRIBED),
        ("Cool Edits मैसेज", Verdict.PASS),
    ],
)
def test_tiktok_rules(text, verdict):
    assert judge(text, TT) == verdict


def test_short_names_dont_match_by_accident():
    short = {**YT, "display_name": "Bo", "identity": "channel:UCx"}
    assert judge("completely unrelated words", short) == Verdict.UNCLEAR


# --- Crediting the right channel ---

ONE = {**YT, "id": 1, "display_name": "First Channel", "identity": "@first"}
TWO = {**YT, "id": 2, "display_name": "Second Studio", "identity": "@second"}
TOK = {**TT, "id": 3, "display_name": "Third Thing", "identity": "@third"}


def test_screenshot_is_credited_to_the_channel_it_names():
    assert choose_target("Second Studio Subscribed", [ONE, TWO, TOK])["id"] == 2


def test_unnamed_screenshot_goes_to_the_platform_it_looks_like():
    assert choose_target("10 Following 5 Followers Message", [ONE, TOK])["id"] == 3
    assert choose_target("1M subscribers Subscribed", [TOK, ONE])["id"] == 1


def test_otherwise_the_next_one_waiting():
    assert choose_target("nothing", [TWO, ONE])["id"] == 2
