"""Postgres schema. Telegram files live in the backup channel, only pointers are stored here."""

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB

metadata = MetaData()


def _now() -> Column:
    return Column("created_at", DateTime(timezone=True), server_default=func.now(), nullable=False)


users = Table(
    "users",
    metadata,
    Column("id", BigInteger, primary_key=True),
    Column("username", String(64)),
    Column("first_name", Text),
    Column("is_banned", Boolean, nullable=False, server_default=text("false")),
    # False once Telegram reports the user blocked the bot or deleted their account.
    Column("is_active", Boolean, nullable=False, server_default=text("true")),
    # The link a user is waiting for while completing force subscribe.
    Column("pending_code", String(64)),
    _now(),
    Index("ix_users_username", "username"),
)

# Owner is not stored: it always comes from OWNER_ID.
roles = Table(
    "roles",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("role", String(16), nullable=False, server_default="moderator"),
    # Once user_id is known it is the only thing that grants access.
    Column("user_id", BigInteger, unique=True),
    Column("username", String(64)),
    Column("added_by", BigInteger),
    _now(),
    Index(
        "uq_roles_unbound_username",
        "username",
        unique=True,
        postgresql_where=text("user_id IS NULL"),
    ),
)

links = Table(
    "links",
    metadata,
    Column("code", String(64), primary_key=True),
    Column("kind", String(16), nullable=False),
    Column("title", Text),
    Column("created_by", BigInteger, nullable=False),
    # Bumped on each edit so two people editing a special link cannot overwrite each other.
    Column("version", Integer, nullable=False, server_default=text("1")),
    _now(),
    Index("ix_links_kind", "kind"),
)

link_items = Table(
    "link_items",
    metadata,
    Column("code", ForeignKey("links.code", ondelete="CASCADE"), primary_key=True),
    Column("position", Integer, primary_key=True, autoincrement=False),
    # Stored per item so old links keep working if the backup channel ever changes.
    Column("channel_id", BigInteger, nullable=False),
    Column("message_id", BigInteger, nullable=False),
    Column("media_group_id", Text),
    Column("file_name", Text),
    Column("file_size", BigInteger),
    Column("caption", Text),
    Column("has_media", Boolean, nullable=False, server_default=text("false")),
)

settings = Table(
    "settings",
    metadata,
    Column("key", String(64), primary_key=True),
    Column("value", JSONB, nullable=False),
)

force_sub_targets = Table(
    "force_sub_targets",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("platform", String(16), nullable=False),
    # Normalised handle, or the chat id for Telegram. Decides whether two entries
    # are the same channel, and so whether earlier verifications still count.
    Column("identity", Text, nullable=False),
    Column("display_name", Text, nullable=False),
    Column("url", Text),
    Column("chat_id", BigInteger),
    # Bumping this makes everybody verify this target again.
    Column("version", Integer, nullable=False, server_default=text("1")),
    # Removal is soft so re-adding the same channel keeps earlier verifications.
    Column("is_active", Boolean, nullable=False, server_default=text("true")),
    _now(),
    UniqueConstraint("platform", "identity", name="uq_target_platform_identity"),
)

verifications = Table(
    "verifications",
    metadata,
    Column("user_id", BigInteger, primary_key=True),
    Column(
        "target_id",
        ForeignKey("force_sub_targets.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("version", Integer, nullable=False),
    Column("method", String(16), nullable=False),
    Column("failed_attempts", Integer, nullable=False, server_default=text("0")),
    Column("verified", Boolean, nullable=False, server_default=text("false")),
    _now(),
)

jobs = Table(
    "jobs",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("kind", String(16), nullable=False),
    Column("status", String(16), nullable=False, server_default="running"),
    Column("created_by", BigInteger, nullable=False),
    Column("payload", JSONB, nullable=False),
    # Where to resume after a restart.
    Column("cursor", BigInteger, nullable=False, server_default=text("0")),
    Column("stats", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    _now(),
    Index("ix_jobs_status", "status"),
)

fsm_state = Table(
    "fsm_state",
    metadata,
    Column("key", Text, primary_key=True),
    Column("state", Text),
    Column("data", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
)
