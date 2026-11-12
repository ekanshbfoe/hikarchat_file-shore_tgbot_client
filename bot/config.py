"""Environment-based configuration."""

import hashlib
import os
from functools import cached_property
from typing import Annotated, Literal

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    bot_token: str
    owner_id: int
    # More people with exactly the owner's power, e.g. "123,456". The owner is the
    # one the bot reports problems to, so they stay named separately.
    extra_owner_ids: Annotated[list[int], NoDecode] = Field(
        default_factory=list, validation_alias=AliasChoices("OWNER_IDS")
    )
    backup_channel_id: int
    database_url: str
    database_direct_url: str | None = None
    moderator_usernames: Annotated[list[str], NoDecode] = Field(default_factory=list)
    dev_chat_id: int | None = None
    # Group the client reads to see activity and review let-through users.
    log_chat_id: int | None = None
    webhook_base_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("WEBHOOK_BASE_URL", "RENDER_EXTERNAL_URL"),
    )
    webhook_secret: str | None = None
    run_mode: Literal["webhook", "polling"] = "webhook"
    port: int = 8080
    local_cache_path: str = "local_cache.sqlite3"
    # Failed screenshots allowed before someone is let through anyway, so a genuine
    # person is never stuck. 0 means keep asking forever.
    screenshot_max_attempts: int = 3
    # Only for a self-hosted Telegram Bot API server. Leave empty normally.
    telegram_api_url: str | None = None

    @field_validator(
        "database_direct_url",
        "dev_chat_id",
        "log_chat_id",
        "webhook_base_url",
        "telegram_api_url",
        mode="before",
    )
    @classmethod
    def _blank_is_none(cls, value):
        return None if value == "" else value

    @field_validator("extra_owner_ids", mode="before")
    @classmethod
    def _split_owner_ids(cls, value):
        if isinstance(value, str):
            value = value.split(",")
        return [int(str(item).strip()) for item in value if str(item).strip()]

    @field_validator("moderator_usernames", mode="before")
    @classmethod
    def _split_usernames(cls, value):
        if isinstance(value, str):
            value = value.split(",")
        return [name.strip().lstrip("@").lower() for name in value if name.strip()]

    @model_validator(mode="after")
    def _use_render_address_if_blank(self):
        # A blank WEBHOOK_BASE_URL would otherwise hide the address Render provides.
        if not self.webhook_base_url:
            self.webhook_base_url = os.environ.get("RENDER_EXTERNAL_URL") or None
        return self

    @property
    def owner_ids(self) -> frozenset[int]:
        """Everybody who has the owner's power, the client included."""
        return frozenset({self.owner_id, *self.extra_owner_ids})

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
