"""A stand-in for Telegram's servers, so whole conversations can be driven in tests.

Real aiogram objects flow through the real dispatcher; only the network call is replaced.
"""

import itertools
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.base import BaseSession
from aiogram.enums import ParseMode
from aiogram.methods import (
    AnswerCallbackQuery,
    CopyMessage,
    CopyMessages,
    CreateChatInviteLink,
    DeleteMyCommands,
    EditChatInviteLink,
    EditMessageCaption,
    EditMessageReplyMarkup,
    EditMessageText,
    GetChat,
    GetChatMember,
    GetFile,
    GetMe,
    GetWebhookInfo,
    SendDocument,
    SendMessage,
    SetMyCommands,
    SetWebhook,
    TelegramMethod,
)
from aiogram.types import (
    CallbackQuery,
    Chat,
    ChatFullInfo,
    ChatInviteLink,
    ChatMemberMember,
    File,
    Message,
    MessageId,
    TelegramObject,
    Update,
    User,
    WebhookInfo,
)

BOT_ID = 42
BOT_USER = User(id=BOT_ID, is_bot=True, first_name="Store", username="store_bot")
_NOW = datetime(2026, 1, 1, tzinfo=UTC)


class FakeSession(BaseSession):
    def __init__(self) -> None:
        super().__init__()
        self.calls: list[TelegramMethod] = []
        self.overrides: dict[type, Any] = {}
        self.file_bytes: bytes = b""
        self._ids = itertools.count(1000)

    def set(self, method: type, result: Any) -> None:
        """Result may be a value, a callable taking the method, or an exception to raise."""
        self.overrides[method] = result

    async def close(self) -> None:
        return None

    async def make_request(self, bot: Bot, method: TelegramMethod, timeout=None) -> Any:
        self.calls.append(method)
        kind = type(method)
        if kind in self.overrides:
            result = self.overrides[kind]
            if isinstance(result, Exception):
                raise result
            return self._mount(result(method) if callable(result) else result, bot)
        return self._mount(self._default(method), bot)

    @staticmethod
    def _mount(result: Any, bot: Bot) -> Any:
        # Real responses come back attached to the bot, so message.edit_text() works.
        if isinstance(result, TelegramObject):
            result.as_(bot)
        return result

    def _message(self, chat_id: int, text: str | None = None) -> Message:
        return Message(
            message_id=next(self._ids),
            date=_NOW,
            chat=Chat(id=chat_id, type="private"),
            text=text,
        )

    def _default(self, method: TelegramMethod) -> Any:
        match method:
            case GetMe():
                return BOT_USER
            case SendMessage():
                return self._message(method.chat_id, method.text)
            case SendDocument():
                return self._message(method.chat_id)
            case CopyMessage():
                return MessageId(message_id=next(self._ids))
            case CopyMessages():
                return [MessageId(message_id=next(self._ids)) for _ in method.message_ids]
            case EditMessageText():
                return self._message(method.chat_id or 0, method.text)
            case EditMessageCaption() | EditMessageReplyMarkup():
                return self._message(method.chat_id or 0)
            case AnswerCallbackQuery() | SetMyCommands() | DeleteMyCommands() | SetWebhook():
                return True
            case GetChatMember():
                return ChatMemberMember(user=User(id=method.user_id, is_bot=False, first_name="U"))
            case GetChat():
                return ChatFullInfo(
                    id=method.chat_id if isinstance(method.chat_id, int) else -100777,
                    type="channel",
                    title="Chat",
                    accent_color_id=0,
                    max_reaction_count=0,
                    accepted_gift_types={
                        "unlimited_gifts": False,
                        "limited_gifts": False,
                        "unique_gifts": False,
                        "premium_subscription": False,
                        "gifts_from_channels": False,
                    },
                )
            case CreateChatInviteLink() | EditChatInviteLink():
                return ChatInviteLink(
                    invite_link="https://t.me/+newlink",
                    creator=BOT_USER,
                    creates_join_request=False,
                    is_primary=False,
                    is_revoked=False,
                )
            case GetFile():
                return File(file_id=method.file_id, file_unique_id="u", file_path="p/f.jpg")
            case GetWebhookInfo():
                return WebhookInfo(url="", has_custom_certificate=False, pending_update_count=0)
        return self._message(0)

    async def stream_content(
        self, url, headers=None, timeout=30, chunk_size=65536, raise_for_status=True
    ) -> AsyncGenerator[bytes]:
        yield self.file_bytes

    # --- helpers for assertions ---

    def of(self, method: type) -> list:
        return [call for call in self.calls if isinstance(call, method)]

    def texts_to(self, chat_id: int) -> list[str]:
        sent = [c.text for c in self.of(SendMessage) if c.chat_id == chat_id]
        edited = [c.text for c in self.of(EditMessageText) if c.chat_id == chat_id]
        return sent + edited

    def last_text(self, chat_id: int) -> str:
        for call in reversed(self.calls):
            if isinstance(call, (SendMessage, EditMessageText)) and call.chat_id == chat_id:
                return call.text
        raise AssertionError(f"nothing sent to {chat_id}")

    def last_markup(self, chat_id: int):
        for call in reversed(self.calls):
            if isinstance(call, (SendMessage, EditMessageText)) and call.chat_id == chat_id:
                return call.reply_markup
        raise AssertionError(f"nothing sent to {chat_id}")

    def of_edit_text(self, index: int) -> str:
        return self.of(EditMessageText)[index].text

    def clear(self) -> None:
        self.calls.clear()


def make_bot(session: FakeSession) -> Bot:
    return Bot(
        "42:TEST",
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


class Chatter:
    """Sends updates as a particular person."""

    _update_ids = itertools.count(1)
    _message_ids = itertools.count(1)

    def __init__(self, dispatcher, bot, user_id: int, username: str | None = None):
        self.dispatcher = dispatcher
        self.bot = bot
        self.user = User(id=user_id, is_bot=False, first_name="Name", username=username)

    def _chat(self) -> Chat:
        return Chat(id=self.user.id, type="private")

    def message(self, **fields) -> Message:
        fields.setdefault("chat", self._chat())
        fields.setdefault("from_user", self.user)
        return Message(message_id=next(self._message_ids), date=_NOW, **fields)

    async def feed(self, **update_fields) -> None:
        update = Update(update_id=next(self._update_ids), **update_fields)
        await self.dispatcher.feed_update(self.bot, update)

    async def send(self, text: str | None = None, **fields) -> Message:
        message = self.message(text=text, **fields)
        await self.feed(message=message)
        return message

    async def tap(self, data: str, message: Message | None = None) -> None:
        origin = message or self.message(text="menu")
        callback = CallbackQuery(
            id=str(next(self._update_ids)),
            from_user=self.user,
            chat_instance="x",
            data=data,
            message=origin,
        )
        await self.feed(callback_query=callback)


def button_data(markup) -> list[str]:
    return [b.callback_data for row in markup.inline_keyboard for b in row if b.callback_data]


def button_urls(markup) -> list[str]:
    return [b.url for row in markup.inline_keyboard for b in row if b.url]
