"""The real web application with Telegram's calls faked."""

import asyncio

import pytest
from aiogram.methods import GetWebhookInfo, SendMessage, SetWebhook
from aiogram.types import WebhookInfo

from bot import main, texts
from bot.main import build_web_app, ensure_webhook, prepare
from tests.helpers import OWNER_ID


@pytest.fixture
def config(world):
    world.app.config.webhook_base_url = "https://bot.example.com"
    return world.app.config


def update_json(update_id=1, user_id=5, text="hello"):
    return {
        "update_id": update_id,
        "message": {
            "message_id": 1,
            "date": 0,
            "chat": {"id": user_id, "type": "private"},
            "from": {"id": user_id, "is_bot": False, "first_name": "A"},
            "text": text,
        },
    }


async def make_client(world, aiohttp_client, ready=True):
    web_app = build_web_app(world.app, world.dispatcher)
    if ready:
        web_app[main.READY].set()
    return await aiohttp_client(web_app), web_app


def headers(config, secret=None):
    return {"X-Telegram-Bot-Api-Secret-Token": secret or config.secret_token}


async def settle():
    # Updates are handled in the background after Telegram gets its answer.
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    for _ in range(50):
        await asyncio.sleep(0.02)
    return tasks


async def test_real_update_reaches_the_bot(world, config, aiohttp_client):
    client, _ = await make_client(world, aiohttp_client)
    response = await client.post(config.webhook_path, json=update_json(), headers=headers(config))
    assert response.status == 200
    await settle()
    assert world.telegram.last_text(5) == texts.UNKNOWN_MESSAGE


async def test_wrong_secret_is_refused(world, config, aiohttp_client):
    client, _ = await make_client(world, aiohttp_client)
    response = await client.post(
        config.webhook_path, json=update_json(), headers=headers(config, "wrong")
    )
    assert response.status == 401
    await settle()
    assert not world.telegram.of(SendMessage)


async def test_missing_secret_is_refused(world, config, aiohttp_client):
    client, _ = await make_client(world, aiohttp_client)
    response = await client.post(config.webhook_path, json=update_json())
    assert response.status == 401


async def test_other_paths_dont_exist(world, config, aiohttp_client):
    client, _ = await make_client(world, aiohttp_client)
    response = await client.post("/webhook/guess", json=update_json(), headers=headers(config))
    assert response.status == 404


async def test_telegram_is_told_to_retry_until_startup_finishes(world, config, aiohttp_client):
    client, web_app = await make_client(world, aiohttp_client, ready=False)
    response = await client.post(config.webhook_path, json=update_json(), headers=headers(config))
    assert response.status == 503
    assert (await client.get("/health")).status == 200  # Render still sees a healthy service.
    web_app[main.READY].set()
    response = await client.post(config.webhook_path, json=update_json(), headers=headers(config))
    assert response.status == 200


async def test_webhook_is_set_once_and_left_alone_after(world, config):
    await ensure_webhook(world.app)
    call = world.telegram.of(SetWebhook)[0]
    assert call.url == config.webhook_url
    assert call.secret_token == config.secret_token
    assert set(call.allowed_updates) == set(main.ALLOWED_UPDATES)

    world.telegram.clear()
    world.telegram.set(
        GetWebhookInfo,
        WebhookInfo(url=config.webhook_url, has_custom_certificate=False, pending_update_count=0),
    )
    await ensure_webhook(world.app)
    assert not world.telegram.of(SetWebhook)


async def test_webhook_is_reset_when_address_changes(world, config):
    await ensure_webhook(world.app)
    world.telegram.clear()
    world.telegram.set(
        GetWebhookInfo,
        WebhookInfo(
            url="https://old.example.com", has_custom_certificate=False, pending_update_count=0
        ),
    )
    await ensure_webhook(world.app)
    assert world.telegram.of(SetWebhook)


async def test_join_requests_are_subscribed_to():
    assert "chat_join_request" in main.ALLOWED_UPDATES


async def test_prepare_seeds_moderators_and_checks_channel(world, config, monkeypatch):
    async def no_migrations(url):
        return None

    monkeypatch.setattr(main, "run_migrations", no_migrations)
    config.moderator_usernames = ["seedmod"]
    await prepare(world.app, "unused")
    assert [m["username"] for m in await world.app.roles.list_moderators()] == ["seedmod"]


async def test_startup_retries_until_it_works(world, config, monkeypatch):
    monkeypatch.setattr(main, "STARTUP_RETRY_SECONDS", 0)
    attempts = []

    async def flaky(app, url):
        attempts.append(1)
        if len(attempts) < 3:
            raise OSError("database asleep")

    monkeypatch.setattr(main, "prepare", flaky)
    ready = asyncio.Event()

    async def after_ready():
        return None

    await main._prepare_until_ready(world.app, "x", ready, after_ready)
    assert ready.is_set() and len(attempts) == 3


async def test_full_conversation_through_the_webhook(world, config, aiohttp_client):
    client, _ = await make_client(world, aiohttp_client)
    await client.post(
        config.webhook_path,
        json=update_json(user_id=OWNER_ID, text="/ban 77"),
        headers=headers(config),
    )
    await settle()
    assert await world.app.users.is_banned(77)
