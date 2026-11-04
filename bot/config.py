"""Environment-based configuration."""

import hashlib
from functools import cached_property
from typing import Annotated, Literal

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    bot_token: str
    owner_id: int
    backup_channel_id: int
    database_url: str
    database_direct_url: str | None = None
    moderator_usernames: Annotated[list[str], NoDecode] = Field(default_factory=list)
    dev_chat_id: int | None = None
    webhook_base_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("WEBHOOK_BASE_URL", "RENDER_EXTERNAL_URL"),
    )
    webhook_secret: str | None = None
    run_mode: Literal["webhook", "polling"] = "webhook"
    port: int = 8080
    local_cache_path: str = "local_cache.sqlite3"

    @field_validator("database_direct_url", "dev_chat_id", "webhook_base_url", mode="before")
    @classmethod
    def _blank_is_none(cls, value):
        return None if value == "" else value

    @field_validator("moderator_usernames", mode="before")
    @classmethod
    def _split_usernames(cls, value):
        if isinstance(value, str):
            value = value.split(",")
        return [name.strip().lstrip("@").lower() for name in value if name.strip()]

    @cached_property
    def secret_token(self) -> str:
        """Secret Telegram must present on webhook calls. Stable across restarts."""
        if self.webhook_secret:
            return self.webhook_secret
        return hashlib.sha256(f"webhook:{self.bot_token}".encode()).hexdigest()

    @cached_property
    def webhook_path(self) -> str:
        return f"/webhook/{hashlib.sha256(self.bot_token.encode()).hexdigest()[:32]}"

    @property
    def webhook_url(self) -> str:
        if not self.webhook_base_url:
            raise ValueError("WEBHOOK_BASE_URL or RENDER_EXTERNAL_URL must be set")
        return f"{self.webhook_base_url.rstrip('/')}{self.webhook_path}"
