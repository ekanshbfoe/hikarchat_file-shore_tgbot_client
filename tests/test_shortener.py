import pytest

from bot import texts
from bot.db.links import Item
from bot.services import share
from bot.services.shortener import _read_result, clean_site, is_link, shorten
from tests.helpers import OWNER_ID


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("example.com", "example.com"),
        ("https://Example.com/", "example.com"),
        ("http://a.example.co.uk/path", "a.example.co.uk"),
        ("not a site", None),
        ("localhost", None),
        ("", None),
    ],
)
def test_site_cleaning(text, expected):
    assert clean_site(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("https://x.com/a", True),
        ("http://x.com", True),
        ("ftp://x.com", False),
        ("hello", False),
        ("https://x.com/a b", False),
    ],
)
def test_is_link(text, expected):
    assert is_link(text) is expected


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ('{"status":"success","shortenedUrl":"https://s.io/a"}', "https://s.io/a"),
        ('{"status":"error","message":"bad key"}', None),
        ('{"shortenedUrl":"not a link"}', None),
        ("https://s.io/plain\n", "https://s.io/plain"),
        ("<html>oops</html>", None),
        ("[1,2]", None),
    ],
)
def test_reading_provider_answers(body, expected):
    assert _read_result(body) == expected


async def test_unreachable_provider_returns_nothing():
    assert await shorten("https://x.com", "127.0.0.1.invalid.example", "k") is None


def link_item():
    return [Item(channel_id=-1, message_id=1)]


async def enable(world, site="s.example.com"):
    await world.app.settings.set("shortener", {"site": site, "key": "K", "enabled": True})


async def test_links_are_shortened_and_cached(world, monkeypatch):
    calls = []

    async def fake(url, site, key):
        calls.append((url, site, key))
        return "https://s.io/x"

    monkeypatch.setattr(share, "shorten", fake)
    await enable(world)
    code = await world.app.links.create("genlink", OWNER_ID, link_item())
    assert await share.share_link(world.app, code) == "https://s.io/x"
    assert await share.share_link(world.app, code) == "https://s.io/x"
    assert len(calls) == 1 and calls[0][0].endswith(code)


async def test_failing_shortener_silently_gives_normal_link(world, monkeypatch):
    async def fake(url, site, key):
        return None

    monkeypatch.setattr(share, "shorten", fake)
    await enable(world)
    code = await world.app.links.create("genlink", OWNER_ID, link_item())
    assert await share.share_link(world.app, code) == await share.plain_link(world.app, code)


async def test_turned_off_means_normal_link(world):
    await world.app.settings.set("shortener", {"site": "s", "key": "K", "enabled": False})
    code = await world.app.links.create("genlink", OWNER_ID, link_item())
    assert await share.share_link(world.app, code) == await share.plain_link(world.app, code)


async def test_command_without_setup_differs_by_role(world):
    await world.owner.send("/shortener")
    assert world.telegram.last_text(OWNER_ID) == texts.SHORTENER_NOT_SET_OWNER
    await world.app.roles.add_by_username("m", OWNER_ID)
    await world.person(8, "m").send("/shortener")
    assert world.telegram.last_text(8) == texts.SHORTENER_NOT_SET_MOD


async def test_command_flow(world, monkeypatch):
    from bot.handlers import shortener as handler

    async def fake(url, site, key):
        return "https://s.io/z" if "good" in url else None

    monkeypatch.setattr(handler, "shorten", fake)
    await enable(world)
    await world.owner.send("/shortener")
    await world.owner.send("nonsense")
    assert world.telegram.last_text(OWNER_ID) == texts.SHORTENER_BAD_LINK
    await world.owner.send("https://good.example.com")
    assert "https://s.io/z" in world.telegram.last_text(OWNER_ID)
    await world.owner.send("/shortener")
    await world.owner.send("https://bad.example.com")
    assert world.telegram.last_text(OWNER_ID) == texts.SHORTENER_FAILED


async def test_user_cannot_use_shortener(world):
    await world.person(5).send("/shortener")
    assert world.telegram.last_text(5) == texts.UNKNOWN_MESSAGE
