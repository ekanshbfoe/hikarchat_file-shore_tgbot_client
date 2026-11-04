"""Shareable links and the stored messages behind them."""

import re
import secrets
from dataclasses import asdict, dataclass

from sqlalchemy import delete, func, select, update

from bot.db.models import link_items, links
from bot.db.store import LONG_TTL, SHORT_TTL, Store

CODE_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
SPECIAL = "special"


class StaleEditError(Exception):
    """Someone else changed the link since this person opened it."""


@dataclass
class Item:
    channel_id: int
    message_id: int
    media_group_id: str | None = None
    file_name: str | None = None
    file_size: int | None = None
    caption: str | None = None
    has_media: bool = False


def new_code() -> str:
    """12 random URL-safe characters, so links cannot be guessed or enumerated."""
    return secrets.token_urlsafe(9)


def is_valid_code(code: str) -> bool:
    return bool(CODE_PATTERN.match(code))


def _ttl(link: dict) -> float:
    return SHORT_TTL if link["kind"] == SPECIAL else LONG_TTL


def _row_values(code: str, items: list[Item], start: int = 0) -> list[dict]:
    return [
        {"code": code, "position": start + index, **asdict(item)}
        for index, item in enumerate(items)
    ]


class LinksRepo:
    def __init__(self, store: Store):
        self.store = store

    async def create(
        self, kind: str, created_by: int, items: list[Item], title: str | None = None
    ) -> str:
        code = new_code()
        async with self.store.db.write() as conn:
            await conn.execute(
                links.insert().values(code=code, kind=kind, created_by=created_by, title=title)
            )
            if items:
                await conn.execute(link_items.insert(), _row_values(code, items))
        return code

    async def get(self, code: str) -> dict | None:
        if not is_valid_code(code):
            return None

        async def loader(conn):
            link = (await conn.execute(select(links).where(links.c.code == code))).first()
            if link is None:
                return None
            rows = await conn.execute(
                select(link_items).where(link_items.c.code == code).order_by(link_items.c.position)
            )
            return {
                "code": code,
                "kind": link.kind,
                "title": link.title,
                "version": link.version,
                "items": [
                    {key: value for key, value in row._mapping.items() if key != "code"}
                    for row in rows
                ],
            }

        return await self.store.read_through(f"link:{code}", _ttl, loader)

    async def append(self, code: str, items: list[Item]) -> None:
        """Used by background batches, which add messages chunk by chunk."""
        if not items:
            return
        async with self.store.db.write() as conn:
            start = (
                await conn.execute(
                    select(func.coalesce(func.max(link_items.c.position) + 1, 0)).where(
                        link_items.c.code == code
                    )
                )
            ).scalar()
            await conn.execute(link_items.insert(), _row_values(code, items, start))
        await self.store.cache.delete(f"link:{code}")

    async def replace_items(self, code: str, items: list[dict], expected_version: int) -> int:
        """Rewrite an editable link. The link and its code stay the same."""
        async with self.store.db.write() as conn:
            result = await conn.execute(
                update(links)
                .where(links.c.code == code, links.c.version == expected_version)
                .values(version=links.c.version + 1)
                .returning(links.c.version)
            )
            row = result.first()
            if row is None:
                raise StaleEditError
            await conn.execute(delete(link_items).where(link_items.c.code == code))
            if items:
                rows = [
                    {
                        **{k: v for k, v in item.items() if k != "position"},
                        "code": code,
                        "position": i,
                    }
                    for i, item in enumerate(items)
                ]
                await conn.execute(link_items.insert(), rows)
        await self.store.cache.delete(f"link:{code}")
        return row.version

    async def delete(self, code: str) -> None:
        async with self.store.db.write() as conn:
            await conn.execute(delete(links).where(links.c.code == code))
        await self.store.cache.delete(f"link:{code}")

    async def list_special(self, limit: int = 30) -> list[dict]:
        async def loader(conn):
            rows = await conn.execute(
                select(
                    links.c.code, links.c.title, func.count(link_items.c.position).label("items")
                )
                .select_from(links.outerjoin(link_items, links.c.code == link_items.c.code))
                .where(links.c.kind == SPECIAL)
                .group_by(links.c.code)
                .order_by(links.c.created_at.desc())
                .limit(limit)
            )
            return [dict(row._mapping) for row in rows]

        return await self.store.db.read(loader)

    async def export_all(self) -> list[dict]:
        async def loader(conn):
            all_links = await conn.execute(
                select(links.c.code, links.c.kind, links.c.title, links.c.version)
            )
            items = await conn.execute(
                select(
                    link_items.c.code,
                    link_items.c.position,
                    link_items.c.channel_id,
                    link_items.c.message_id,
                ).order_by(link_items.c.code, link_items.c.position)
            )
            grouped: dict[str, list] = {}
            for row in items:
                grouped.setdefault(row.code, []).append([row.channel_id, row.message_id])
            return [
                {
                    "code": row.code,
                    "kind": row.kind,
                    "title": row.title,
                    "items": grouped.get(row.code, []),
                }
                for row in all_links
            ]

        return await self.store.db.read(loader)
