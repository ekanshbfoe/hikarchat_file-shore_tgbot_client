"""HTTP routes that are not part of the Telegram webhook."""

from aiohttp import web


async def health(_: web.Request) -> web.Response:
    """Answer uptime monitors instantly. Must never touch the database,
    otherwise constant pings would stop a scale-to-zero database from sleeping."""
    return web.Response(text="ok")


def add_health_routes(app: web.Application) -> None:
    # add_get also answers HEAD, which some uptime monitors use.
    app.router.add_get("/health", health)
    app.router.add_get("/keepalive", health)
    app.router.add_get("/", health)
