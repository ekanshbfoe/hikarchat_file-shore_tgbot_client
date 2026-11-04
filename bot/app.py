"""Everything handlers need, passed as one object."""

from dataclasses import dataclass, field

from aiogram import Bot

from bot.config import Settings
from bot.db.jobs import JobsRepo
from bot.db.links import LinksRepo
from bot.db.roles import RolesRepo
from bot.db.settings import SettingsRepo
from bot.db.store import Store
from bot.db.targets import TargetsRepo
from bot.db.users import UsersRepo


@dataclass
class App:
    config: Settings
    bot: Bot
    store: Store
    users: UsersRepo = field(init=False)
    roles: RolesRepo = field(init=False)
    settings: SettingsRepo = field(init=False)
    links: LinksRepo = field(init=False)
    targets: TargetsRepo = field(init=False)
    jobs: JobsRepo = field(init=False)
    runner: object = None

    def __post_init__(self) -> None:
        self.users = UsersRepo(self.store)
        self.roles = RolesRepo(self.store, self.config.owner_id)
        self.settings = SettingsRepo(self.store)
        self.links = LinksRepo(self.store)
        self.targets = TargetsRepo(self.store)
        self.jobs = JobsRepo(self.store)

    async def bot_username(self) -> str:
        me = await self.bot.me()
        return me.username
