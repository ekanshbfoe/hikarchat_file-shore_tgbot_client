from bot.db.audit import AuditRepo
from bot.db.links import LinksRepo
from bot.db.local_cache import LocalCache
from bot.db.roles import RolesRepo
from bot.db.settings import SettingsRepo
from bot.db.store import Store
from bot.db.targets import TargetsRepo
from bot.db.users import UsersRepo

OWNER_ID = 1000


class Repos:
    def __init__(self, store: Store):
        self.store = store
        self.users = UsersRepo(store)
        self.roles = RolesRepo(store, OWNER_ID)
        self.settings = SettingsRepo(store)
        self.links = LinksRepo(store)
        self.targets = TargetsRepo(store)
        self.audit = AuditRepo(store)

    async def forget_local(self) -> None:
        """Simulate Render wiping the disk."""
        await self.store.cache.delete_prefix("")


async def open_cache(path) -> LocalCache:
    cache = LocalCache(str(path))
    await cache.open()
    return cache
