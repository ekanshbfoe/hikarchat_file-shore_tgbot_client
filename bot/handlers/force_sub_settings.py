"""Settings → Force Subscribe. The owner adds or removes any number of Telegram channels,
Telegram groups, YouTube channels and TikTok profiles, whenever they like."""

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    ChatAdministratorRights,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    KeyboardButtonRequestChat,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

from bot import texts
from bot.app import App
from bot.db.targets import SOCIAL, TELEGRAM, TIKTOK, YOUTUBE, AddStatus
from bot.filters import IsInput, IsOwner
from bot.services.social_links import VideoLinkError, parse_social
from bot.states import ForceSubFlow

router = Router(name="force_sub_settings")
MAX_NAME = 100
REQUEST_CHANNEL = 1
REQUEST_GROUP = 2
INVITE_LINK_NAME = "Force subscribe"

_PLATFORM_NAMES = {
    TELEGRAM: texts.FS_PLATFORM_TELEGRAM,
    YOUTUBE: texts.FS_PLATFORM_YOUTUBE,
    TIKTOK: texts.FS_PLATFORM_TIKTOK,
}


def _button(text: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=data)


async def _home(app: App) -> tuple[str, InlineKeyboardMarkup]:
    targets = await app.targets.list_active()
    rows = [
        [_button(f"{_PLATFORM_NAMES[t['platform']]}: {t['display_name']}", f"fs:item:{t['id']}")]
        for t in targets
    ]
    rows += [
        [
            _button(texts.FS_ADD_TELEGRAM_CHANNEL, "fs:add:channel"),
            _button(texts.FS_ADD_TELEGRAM_GROUP, "fs:add:group"),
        ],
        [
            _button(texts.FS_ADD_YOUTUBE, f"fs:add:{YOUTUBE}"),
            _button(texts.FS_ADD_TIKTOK, f"fs:add:{TIKTOK}"),
        ],
        [_button(texts.BTN_BACK, "set:home")],
    ]
    items = "\n".join(
        f"• {texts.esc(t['display_name'])} ({_PLATFORM_NAMES[t['platform']]})" for t in targets
    )
    return texts.FS_VIEW.format(items=items or texts.FS_NONE), InlineKeyboardMarkup(
        inline_keyboard=rows
    )


def _item(target: dict) -> tuple[str, InlineKeyboardMarkup]:
    target_id = target["id"]
    rows = [
        [_button(texts.FS_EDIT_NAME, f"fs:rename:{target_id}")],
        [_button(texts.FS_REPLACE, f"fs:replace:{target_id}")],
    ]
    if target["platform"] in SOCIAL:
        rows.append([_button(texts.FS_ASK_AGAIN, f"fs:ask:{target_id}")])
    rows += [
        [_button(texts.FS_REMOVE, f"fs:rm:{target_id}")],
        [_button(texts.BTN_BACK, "fs:home")],
    ]
    text = texts.FS_ITEM_VIEW.format(
        name=texts.esc(target["display_name"]),
        platform=_PLATFORM_NAMES[target["platform"]],
        url=texts.esc(target["url"] or ""),
    )
    return text, InlineKeyboardMarkup(inline_keyboard=rows)


async def _show(callback: CallbackQuery, text: str, markup: InlineKeyboardMarkup) -> None:
    try:
        await callback.message.edit_text(text, reply_markup=markup)
    except TelegramBadRequest:
        pass  # A double tap: the screen already shows this.


async def _active_target(callback: CallbackQuery, app: App) -> dict | None:
    target = await app.targets.get(int(callback.data.rsplit(":", 1)[1]))
    if target is None or not target["is_active"]:
        await callback.answer(texts.BUTTON_EXPIRED)
        return None
    return target


@router.callback_query(F.data == "fs:home", IsOwner())
async def home(callback: CallbackQuery, state: FSMContext, app: App) -> None:
    await state.clear()
    await _show(callback, *await _home(app))
    await callback.answer()


@router.callback_query(F.data.startswith("fs:item:"), IsOwner())
async def item(callback: CallbackQuery, state: FSMContext, app: App) -> None:
    await state.clear()
    target = await _active_target(callback, app)
    if target:
        await _show(callback, *_item(target))
        await callback.answer()


@router.callback_query(F.data.startswith("fs:rm:"), IsOwner())
async def remove(callback: CallbackQuery, app: App) -> None:
    target = await _active_target(callback, app)
    if target:
        await app.targets.remove(target["id"])
        await callback.answer(texts.FS_REMOVED, show_alert=True)
        await _show(callback, *await _home(app))


@router.callback_query(F.data.startswith("fs:ask:"), IsOwner())
async def ask_again_confirm(callback: CallbackQuery, app: App) -> None:
    target = await _active_target(callback, app)
    if target:
        markup = InlineKeyboardMarkup(
            inline_keyboard=[
                [_button(texts.FS_ASK_AGAIN_YES, f"fs:askyes:{target['id']}")],
                [_button(texts.BTN_BACK, f"fs:item:{target['id']}")],
            ]
        )
        name = texts.esc(target["display_name"])
        await _show(callback, texts.FS_ASK_AGAIN_CONFIRM.format(name=name), markup)
        await callback.answer()


@router.callback_query(F.data.startswith("fs:askyes:"), IsOwner())
async def ask_again(callback: CallbackQuery, app: App) -> None:
    target = await _active_target(callback, app)
    if target:
        await app.targets.ask_everyone_again(target["id"])
        await callback.answer()
        await callback.message.answer(
            texts.FS_ASK_AGAIN_DONE.format(name=texts.esc(target["display_name"]))
        )
        await _show(callback, *await _home(app))


# --- Fixing a name ---


@router.callback_query(F.data.startswith("fs:rename:"), IsOwner())
async def rename_start(callback: CallbackQuery, state: FSMContext, app: App) -> None:
    target = await _active_target(callback, app)
    if target:
        await state.set_state(ForceSubFlow.rename)
        await state.update_data(target_id=target["id"])
        await callback.answer()
        await callback.message.answer(texts.FS_NAME_PROMPT)


@router.message(ForceSubFlow.rename, IsOwner(), IsInput())
async def rename_save(message: Message, state: FSMContext, app: App) -> None:
    name = (message.text or "").strip()
    if not name or len(name) > MAX_NAME:
        await message.answer(texts.FS_NAME_INVALID)
        return
    data = await state.get_data()
    await app.targets.rename(data["target_id"], name)
    await state.clear()
    await message.answer(texts.FS_RENAMED)
    text, markup = await _home(app)
    await message.answer(text, reply_markup=markup)


# --- Adding or replacing ---


@router.callback_query(F.data.startswith("fs:replace:"), IsOwner())
async def replace_start(callback: CallbackQuery, state: FSMContext, app: App) -> None:
    target = await _active_target(callback, app)
    if not target:
        return
    await state.clear()
    await callback.answer()
    if target["platform"] == TELEGRAM:
        await _ask_for_chat(callback.message, state, "channel", replace_id=target["id"])
    else:
        await _ask_for_link(callback.message, state, target["platform"], replace_id=target["id"])


@router.callback_query(F.data.in_({"fs:add:channel", "fs:add:group"}), IsOwner())
async def add_chat(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer()
    await _ask_for_chat(callback.message, state, callback.data.rsplit(":", 1)[1])


@router.callback_query(F.data.in_({f"fs:add:{YOUTUBE}", f"fs:add:{TIKTOK}"}), IsOwner())
async def add_social(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer()
    await _ask_for_link(callback.message, state, callback.data.rsplit(":", 1)[1])


async def _ask_for_chat(
    message: Message, state: FSMContext, kind: str, replace_id: int | None = None
) -> None:
    await state.set_state(ForceSubFlow.pick_chat)
    await state.update_data(replace_id=replace_id, kind=kind)
    # Telegram offers to add the bot as admin with these rights as part of choosing.
    rights = ChatAdministratorRights(
        is_anonymous=False,
        can_manage_chat=False,
        can_delete_messages=False,
        can_manage_video_chats=False,
        can_restrict_members=False,
        can_promote_members=False,
        can_change_info=False,
        can_invite_users=True,
        can_post_stories=False,
        can_edit_stories=False,
        can_delete_stories=False,
        can_send_welcome_messages=False,
    )
    is_channel = kind == "channel"
    request = KeyboardButtonRequestChat(
        request_id=REQUEST_CHANNEL if is_channel else REQUEST_GROUP,
        chat_is_channel=is_channel,
        user_administrator_rights=rights,
        bot_administrator_rights=rights,
        request_title=True,
        request_username=True,
    )
    await message.answer(
        texts.FS_PICK_CHANNEL if is_channel else texts.FS_PICK_GROUP,
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[
                [
                    KeyboardButton(
                        text=texts.FS_PICK_BUTTON_CHANNEL
                        if is_channel
                        else texts.FS_PICK_BUTTON_GROUP,
                        request_chat=request,
                    )
                ]
            ],
            resize_keyboard=True,
            one_time_keyboard=True,
        ),
    )


async def _invite_url(app: App, chat) -> str | None:
    if chat.username:
        return f"https://t.me/{chat.username}"
    try:
        link = await app.bot.create_chat_invite_link(chat.id, name=INVITE_LINK_NAME)
    except (TelegramBadRequest, TelegramForbiddenError):
        return None
    return link.invite_link


@router.message(ForceSubFlow.pick_chat, IsOwner(), F.chat_shared)
async def chat_picked(message: Message, state: FSMContext, app: App) -> None:
    chat_id = message.chat_shared.chat_id
    gone = ReplyKeyboardRemove()
    try:
        chat = await app.bot.get_chat(chat_id)
        me = await app.bot.get_chat_member(chat_id, app.bot.id)
    except (TelegramBadRequest, TelegramForbiddenError):
        await state.clear()
        await message.answer(texts.FS_CHAT_UNREACHABLE, reply_markup=gone)
        return
    name = chat.title or chat.username or str(chat_id)
    url = await _invite_url(app, chat) if me.status in ("administrator", "creator") else None
    if url is None:
        await state.clear()
        await message.answer(texts.FS_NOT_ADMIN.format(name=texts.esc(name)), reply_markup=gone)
        return
    data = await state.get_data()
    await state.clear()
    if data.get("replace_id"):
        try:
            target, status = await app.targets.replace(
                data["replace_id"], str(chat_id), name, url, chat_id=chat_id
            )
        except LookupError:
            await message.answer(texts.BUTTON_EXPIRED, reply_markup=gone)
            return
        await _report(message, target, status, replaced=True, markup=gone)
    else:
        target, status = await app.targets.add(TELEGRAM, str(chat_id), name, url, chat_id=chat_id)
        await _report(message, target, status, markup=gone)
    text, markup = await _home(app)
    await message.answer(text, reply_markup=markup)


@router.message(ForceSubFlow.pick_chat, IsOwner(), IsInput())
async def chat_not_picked(message: Message) -> None:
    await message.answer(texts.FS_PICK_FALLBACK)


async def _ask_for_link(
    message: Message, state: FSMContext, platform: str, replace_id: int | None = None
) -> None:
    await state.set_state(ForceSubFlow.link)
    await state.update_data(platform=platform, replace_id=replace_id)
    await message.answer(
        texts.FS_LINK_PROMPT_YOUTUBE if platform == YOUTUBE else texts.FS_LINK_PROMPT_TIKTOK
    )


@router.message(ForceSubFlow.link, IsOwner(), IsInput())
async def link_received(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    platform = data["platform"]
    invalid = texts.FS_LINK_INVALID_YOUTUBE if platform == YOUTUBE else texts.FS_LINK_INVALID_TIKTOK
    text = (message.text or "").strip()
    if not text:
        await message.answer(invalid)
        return
    try:
        parsed = await parse_social(platform, text)
    except VideoLinkError:
        await message.answer(texts.FS_LINK_VIDEO_YOUTUBE)
        return
    if parsed is None:
        await message.answer(invalid)
        return
    await state.update_data(identity=parsed.identity, url=parsed.url)
    await state.set_state(ForceSubFlow.name)
    await message.answer(texts.FS_NAME_PROMPT)


@router.message(ForceSubFlow.name, IsOwner(), IsInput())
async def name_received(message: Message, state: FSMContext, app: App) -> None:
    name = (message.text or "").strip()
    if not name or len(name) > MAX_NAME:
        await message.answer(texts.FS_NAME_INVALID)
        return
    data = await state.get_data()
    await state.clear()
    if data.get("replace_id"):
        try:
            target, status = await app.targets.replace(
                data["replace_id"], data["identity"], name, data["url"]
            )
        except LookupError:
            await message.answer(texts.BUTTON_EXPIRED)
            return
        await _report(message, target, status, replaced=True)
    else:
        target, status = await app.targets.add(
            data["platform"], data["identity"], name, data["url"]
        )
        await _report(message, target, status)
    text, markup = await _home(app)
    await message.answer(text, reply_markup=markup)


async def _report(
    message: Message, target: dict, status: AddStatus, replaced: bool = False, markup=None
) -> None:
    name = texts.esc(target["display_name"])
    if status == AddStatus.ALREADY:
        template = texts.FS_ALREADY
    elif status == AddStatus.READDED:
        template = texts.FS_READDED
    else:
        template = texts.FS_REPLACED if replaced else texts.FS_ADDED
    await message.answer(template.format(name=name), reply_markup=markup)
