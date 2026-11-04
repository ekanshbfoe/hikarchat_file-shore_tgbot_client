import pytest
from aiohttp import web

from bot.web import add_health_routes


@pytest.fixture
async def client(aiohttp_client):
    app = web.Application()
    add_health_routes(app)
    return await aiohttp_client(app)


@pytest.mark.parametrize("path", ["/health", "/keepalive", "/"])
async def test_get_answers_ok(client, path):
    response = await client.get(path)
    assert response.status == 200
    assert await response.text() == "ok"


@pytest.mark.parametrize("path", ["/health", "/keepalive"])
async def test_head_answers_for_uptime_monitors(client, path):
    assert (await client.head(path)).status == 200
