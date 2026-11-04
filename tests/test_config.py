import pytest

from bot.config import Settings

BASE = {
    "bot_token": "123:abc",
    "owner_id": 1,
    "backup_channel_id": -1001,
    "database_url": "postgres://x",
}


def make(**overrides):
    return Settings(_env_file=None, **{**BASE, **overrides})


def test_moderator_usernames_are_normalised():
    settings = make(moderator_usernames=" @Alice, bob ,,")
    assert settings.moderator_usernames == ["alice", "bob"]


def test_webhook_secret_is_stable_and_allowed_by_telegram():
    assert make().secret_token == make().secret_token
    assert make().secret_token.isalnum()


def test_webhook_path_does_not_expose_token():
    assert "abc" not in make().webhook_path.split("/webhook/")[0]
    assert "123:abc" not in make().webhook_path


def test_webhook_url_joins_cleanly():
    settings = make(webhook_base_url="https://x.onrender.com/")
    assert settings.webhook_url.startswith("https://x.onrender.com/webhook/")


def test_webhook_url_needs_a_base():
    with pytest.raises(ValueError):
        _ = make().webhook_url


def test_render_external_url_is_used(monkeypatch):
    monkeypatch.setenv("RENDER_EXTERNAL_URL", "https://y.onrender.com")
    assert Settings(_env_file=None, **BASE).webhook_base_url == "https://y.onrender.com"
