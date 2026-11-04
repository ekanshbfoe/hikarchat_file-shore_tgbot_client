import pytest

from bot.db.targets import TIKTOK, YOUTUBE
from bot.services import social_links
from bot.services.social_links import VideoLinkError, parse_social, parse_tiktok, parse_youtube


@pytest.mark.parametrize(
    ("text", "identity"),
    [
        ("https://www.youtube.com/@MyChannel", "@mychannel"),
        ("https://youtube.com/@MyChannel?si=abc123", "@mychannel"),
        ("youtube.com/@mychannel/videos", "@mychannel"),
        ("https://m.youtube.com/@mychannel", "@mychannel"),
        ("@MyChannel", "@mychannel"),
        ("  https://www.youtube.com/@mychannel/  ", "@mychannel"),
        ("https://www.youtube.com/channel/UCabcDEF", "channel:UCabcDEF"),
        ("https://www.youtube.com/c/SomeName", "c:somename"),
        ("https://www.youtube.com/user/SomeName", "user:somename"),
    ],
)
def test_youtube_channel_forms(text, identity):
    assert parse_youtube(text).identity == identity


def test_same_channel_gets_same_identity_however_it_is_written():
    forms = ["https://youtube.com/@Me?si=1", "@me", "https://m.youtube.com/@ME/featured"]
    assert len({parse_youtube(form).identity for form in forms}) == 1


@pytest.mark.parametrize(
    "text",
    [
        "https://youtu.be/abc",
        "https://www.youtube.com/watch?v=abc",
        "https://youtube.com/shorts/abc",
        "https://www.youtube.com/playlist?list=abc",
    ],
)
def test_youtube_video_links_are_recognised(text):
    with pytest.raises(VideoLinkError):
        parse_youtube(text)


@pytest.mark.parametrize(
    "text", ["hello", "https://google.com/@x", "https://youtube.com/", "https://youtube.com/about"]
)
def test_youtube_nonsense(text):
    assert parse_youtube(text) is None


@pytest.mark.parametrize(
    "text",
    [
        "https://www.tiktok.com/@MyName",
        "https://tiktok.com/@myname?lang=en",
        "tiktok.com/@myname/video/123",
        "https://m.tiktok.com/@myname",
        "@myname",
    ],
)
async def test_tiktok_forms(text):
    assert (await parse_tiktok(text)).identity == "@myname"


@pytest.mark.parametrize("text", ["hello", "https://google.com/@x", "https://tiktok.com/about"])
async def test_tiktok_nonsense(text):
    assert await parse_tiktok(text) is None


@pytest.mark.parametrize(
    "link", ["https://vm.tiktok.com/ZMabc/", "vt.tiktok.com/ZMabc", "https://tiktok.com/t/ZMabc/"]
)
async def test_tiktok_short_links_are_followed(monkeypatch, link):
    async def follow(url):
        assert url.startswith("https://")
        return "https://www.tiktok.com/@realname/video/1?x=y"

    monkeypatch.setattr(social_links, "_follow_redirect", follow)
    assert (await parse_tiktok(link)).identity == "@realname"


async def test_tiktok_short_link_that_cant_be_followed(monkeypatch):
    async def follow(url):
        return None

    monkeypatch.setattr(social_links, "_follow_redirect", follow)
    assert await parse_tiktok("https://vm.tiktok.com/ZMabc/") is None


async def test_platform_dispatch():
    assert (await parse_social(YOUTUBE, "@a")).url.startswith("https://www.youtube.com/")
    assert (await parse_social(TIKTOK, "@a")).url.startswith("https://www.tiktok.com/")
