"""/settings. Owner only."""

import re
from datetime import datetime

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot import texts
from bot.app import App
from bot.db.roles import AddResult
from bot.filters import IsInput, IsOwner
from bot.menus import clear_menu
from bot.services import backup
from bot.services.shortener import clean_site, is_link, shorten
from bot.states import SettingsFlow

router = Router(name="settings")
MAX_CAPTION = 1000
MAX_BUTTON_TEXT = 60
_BUTTON = re.compile(r"^(.+?)\s+[-–—]\s+(https?://\S+|tg://\S+)$", re.S)


def _button(text: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=data)


def _keyboard(*rows: list[InlineKeyboardButton]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=list(rows))


BACK = _button(texts.BTN_BACK, "set:home")


async def _home(app: App) -> InlineKeyboardMarkup:
    protect = await app.settings.get("protect_content", False)
    return _keyboard(
        [_button(texts.BTN_BACKUP, "set:backup")],
        [_button(texts.BTN_SHORTENER, "set:short")],
        [_button(texts.BTN_CAPTION, "set:caption")],
        [_button(texts.BTN_BUTTON, "set:button")],
        [_button(texts.BTN_PROTECT_ON if protect else texts.BTN_PROTECT_OFF, "set:protect")],
        [_button(texts.BTN_FORCE_SUB, "fs:home")],
        [_button(texts.BTN_MODERATORS, "set:mods")],
        [_button(texts.BTN_SET_UPDATE_CHANNEL, "set:update")],
    )


async def _show(callback: CallbackQuery, text: str, markup: InlineKeyboardMarkup) -> None:
    try:
        await callback.message.edit_text(text, reply_markup=markup)
    except TelegramBadRequest:
        pass  # A double tap: the screen already shows this.


@router.message(Command("settings"), IsOwner())
async def settings(message: Message, state: FSMContext, app: App) -> None:
    await state.clear()
    await message.answer(texts.SETTINGS_TITLE, reply_markup=await _home(app))


@router.callback_query(F.data == "set:home", IsOwner())
async def home(callback: CallbackQuery, state: FSMContext, app: App) -> None:
    await state.clear()
    await _show(callback, texts.SETTINGS_TITLE, await _home(app))
    await callback.answer()


# --- Protect content ---


@router.callback_query(F.data == "set:protect", IsOwner())
async def toggle_protect(callback: CallbackQuery, app: App) -> None:
    now_on = not await app.settings.get("protect_content", False)
    await app.settings.set("protect_content", now_on)
    await callback.answer(texts.PROTECT_ON if now_on else texts.PROTECT_OFF)
    await _show(callback, texts.SETTINGS_TITLE, await _home(app))


# --- Custom caption ---


async def _caption_view(app: App) -> tuple[str, InlineKeyboardMarkup]:
    caption = await app.settings.get("custom_caption")
    rows = [[_button(texts.BTN_CHANGE, "set:caption:edit")]]
    if caption:
        rows.append([_button(texts.BTN_REMOVE, "set:caption:rm")])
    rows.append([BACK])
    current = texts.esc(caption) if caption else texts.NOT_SET
    return texts.CAPTION_VIEW.format(current=current), _keyboard(*rows)


@router.callback_query(F.data == "set:caption", IsOwner())
async def caption_view(callback: CallbackQuery, state: FSMContext, app: App) -> None:
    await state.clear()
    await _show(callback, *await _caption_view(app))
    await callback.answer()


@router.callback_query(F.data == "set:caption:edit", IsOwner())
async def caption_edit(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(SettingsFlow.caption)
    await callback.answer()
    await callback.message.answer(texts.CAPTION_PROMPT)


@router.message(SettingsFlow.caption, IsOwner(), IsInput())
async def caption_save(message: Message, state: FSMContext, app: App) -> None:
    caption = (message.text or message.caption or "").strip()
    if not caption or len(caption) > MAX_CAPTION:
        await message.answer(texts.CAPTION_TOO_LONG)
        return
    await app.settings.set("custom_caption", caption)
    await state.clear()
    text, markup = await _caption_view(app)
    await message.answer(texts.CAPTION_SAVED)
    await message.answer(text, reply_markup=markup)


@router.callback_query(F.data == "set:caption:rm", IsOwner())
async def caption_remove(callback: CallbackQuery, app: App) -> None:
    await app.settings.set("custom_caption", "")
    await callback.answer(texts.CAPTION_REMOVED)
    await _show(callback, *await _caption_view(app))


# --- Custom button ---


async def _button_view(app: App) -> tuple[str, InlineKeyboardMarkup]:
    button = await app.settings.get("custom_button")
    rows = [[_button(texts.BTN_CHANGE, "set:button:edit")]]
    if button:
        rows.append([_button(texts.BTN_REMOVE, "set:button:rm")])
    rows.append([BACK])
    current = texts.esc(f"{button['text']} ({button['url']})") if button else texts.NOT_SET
    return texts.BUTTON_VIEW.format(current=current), _keyboard(*rows)


@router.callback_query(F.data == "set:button", IsOwner())
async def button_view(callback: CallbackQuery, state: FSMContext, app: App) -> None:
    await state.clear()
    await _show(callback, *await _button_view(app))
    await callback.answer()


@router.callback_query(F.data == "set:button:edit", IsOwner())
async def button_edit(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(SettingsFlow.button)
    await callback.answer()
    await callback.message.answer(texts.BUTTON_PROMPT)


@router.message(SettingsFlow.button, IsOwner(), IsInput())
async def button_save(message: Message, state: FSMContext, app: App) -> None:
    match = _BUTTON.match((message.text or "").strip())
    if not match or len(match.group(1)) > MAX_BUTTON_TEXT:
        await message.answer(texts.BUTTON_INVALID)
        return
    await app.settings.set("custom_button", {"text": match.group(1), "url": match.group(2)})
    await state.clear()
    text, markup = await _button_view(app)
    await message.answer(texts.BUTTON_SAVED)
    await message.answer(text, reply_markup=markup)


@router.callback_query(F.data == "set:button:rm", IsOwner())
async def button_remove(callback: CallbackQuery, app: App) -> None:
    await app.settings.set("custom_button", {})
    await callback.answer(texts.BUTTON_REMOVED)
    await _show(callback, *await _button_view(app))


# --- Link shortener ---


async def _short_view(app: App) -> tuple[str, InlineKeyboardMarkup]:
    config = await app.settings.get("shortener") or {}
    rows = [[_button(texts.BTN_CHANGE, "set:short:edit")]]
    if config:
        toggle = texts.BTN_TURN_OFF if config.get("enabled") else texts.BTN_TURN_ON
        rows.append([_button(toggle, "set:short:toggle")])
        rows.append([_button(texts.BTN_REMOVE, "set:short:rm")])
    rows.append([BACK])
    status = texts.SHORTENER_STATUS_ON if config.get("enabled") else texts.SHORTENER_STATUS_OFF
    site = texts.esc(config["site"]) if config else texts.NOT_SET
    return texts.SHORTENER_VIEW.format(status=status, site=site), _keyboard(*rows)


@router.callback_query(F.data == "set:short", IsOwner())
async def short_view(callback: CallbackQuery, state: FSMContext, app: App) -> None:
    await state.clear()
    await _show(callback, *await _short_view(app))
    await callback.answer()


@router.callback_query(F.data == "set:short:edit", IsOwner())
async def short_edit(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(SettingsFlow.shortener_site)
    await callback.answer()
    await callback.message.answer(texts.SHORTENER_SITE_PROMPT)


@router.message(SettingsFlow.shortener_site, IsOwner(), IsInput())
async def short_site(message: Message, state: FSMContext) -> None:
    site = clean_site(message.text or "")
    if not site:
        await message.answer(texts.SHORTENER_SITE_INVALID)
        return
    await state.update_data(site=site)
    await state.set_state(SettingsFlow.shortener_key)
    await message.answer(texts.SHORTENER_KEY_PROMPT)


@router.message(SettingsFlow.shortener_key, IsOwner(), IsInput())
async def short_key(message: Message, state: FSMContext, app: App) -> None:
    key = (message.text or "").strip()
    data = await state.get_data()
    # The key is a secret, so don't leave it sitting in the chat.
    try:
        await message.delete()
    except TelegramBadRequest:
        pass
    progress = await message.answer(texts.SHORTENER_CHECKING)
    test_link = f"https://t.me/{await app.bot_username()}"
    if not key or not await shorten(test_link, data["site"], key):
        await state.set_state(SettingsFlow.shortener_site)
        await progress.edit_text(
            texts.SHORTENER_CHECK_FAILED + "\n\n" + texts.SHORTENER_SITE_PROMPT
        )
        return
    await app.settings.set("shortener", {"site": data["site"], "key": key, "enabled": True})
    await state.clear()
    await progress.edit_text(texts.SHORTENER_SAVED)


@router.callback_query(F.data == "set:short:toggle", IsOwner())
async def short_toggle(callback: CallbackQuery, app: App) -> None:
    config = await app.settings.get("shortener")
    if config:
        await app.settings.set("shortener", {**config, "enabled": not config.get("enabled")})
    await _show(callback, *await _short_view(app))
    await callback.answer()


@router.callback_query(F.data == "set:short:rm", IsOwner())
async def short_remove(callback: CallbackQuery, app: App) -> None:
    await app.settings.set("shortener", {})
    await callback.answer(texts.SHORTENER_REMOVED)
    await _show(callback, *await _short_view(app))


# --- Update channel ---


async def _update_view(app: App) -> tuple[str, InlineKeyboardMarkup]:
    current = await app.settings.get("update_channel")
    rows = [[_button(texts.BTN_CHANGE, "set:update:edit")]]
    if current:
        rows.append([_button(texts.BTN_REMOVE, "set:update:rm")])
    rows.append([BACK])
    return texts.UPDATE_CHANNEL_VIEW.format(current=current or texts.NOT_SET), _keyboard(*rows)


@router.callback_query(F.data == "set:update", IsOwner())
async def update_view(callback: CallbackQuery, state: FSMContext, app: App) -> None:
    await state.clear()
    await _show(callback, *await _update_view(app))
    await callback.answer()


@router.callback_query(F.data == "set:update:edit", IsOwner())
async def update_edit(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(SettingsFlow.update_channel)
    await callback.answer()
    await callback.message.answer(texts.UPDATE_CHANNEL_PROMPT)


@router.message(SettingsFlow.update_channel, IsOwner(), IsInput())
async def update_save(message: Message, state: FSMContext, app: App) -> None:
    text = (message.text or "").strip()
    if re.fullmatch(r"@[A-Za-z0-9_]{4,}", text):
        text = f"https://t.me/{text[1:]}"
    if not is_link(text):
        await message.answer(texts.SHORTENER_BAD_LINK)
        return
    await app.settings.set("update_channel", text)
    await state.clear()
    await message.answer(texts.UPDATE_CHANNEL_SAVED)


@router.callback_query(F.data == "set:update:rm", IsOwner())
async def update_remove(callback: CallbackQuery, app: App) -> None:
    await app.settings.set("update_channel", "")
    await callback.answer(texts.UPDATE_CHANNEL_REMOVED)
    await _show(callback, *await _update_view(app))


# --- Backup ---


async def _backup_view(app: App) -> tuple[str, InlineKeyboardMarkup]:
    last = await app.settings.get(backup.LAST_BACKUP)
    shown = (
        datetime.fromisoformat(last).strftime("%d %b %Y, %H:%M UTC") if last else texts.BACKUP_NEVER
    )
    return (
        texts.BACKUP_VIEW.format(last=shown),
        _keyboard([_button(texts.BACKUP_NOW, "set:backup:now")], [BACK]),
    )


@router.callback_query(F.data == "set:backup", IsOwner())
async def backup_view(callback: CallbackQuery, state: FSMContext, app: App) -> None:
    await state.clear()
    await _show(callback, *await _backup_view(app))
    await callback.answer()


@router.callback_query(F.data == "set:backup:now", IsOwner())
async def backup_now(callback: CallbackQuery, app: App) -> None:
    saved = await backup.run_backup(app)
    await callback.answer(texts.BACKUP_DONE if saved else texts.BACKUP_FAILED, show_alert=True)
    await _show(callback, *await _backup_view(app))


# --- Moderators ---


async def _mods_view(app: App) -> tuple[str, InlineKeyboardMarkup]:
    moderators = await app.roles.list_moderators()
    rows = [[_button(texts.MODERATOR_ADD, "set:mods:add")]]
    lines = []
    for moderator in moderators:
        name = (
            f"@{moderator['username']}"
            if moderator["username"]
            else moderator["first_name"] or str(moderator["user_id"])
        )
        lines.append(f"• {texts.esc(name)}")
        rows.append([_button(f"{texts.BTN_REMOVE} {name}", f"set:mods:rm:{moderator['id']}")])
    rows.append([BACK])
    names = "\n".join(lines) or texts.MODERATORS_NONE
    return texts.MODERATORS_VIEW.format(names=names), _keyboard(*rows)


@router.callback_query(F.data == "set:mods", IsOwner())
async def mods_view(callback: CallbackQuery, state: FSMContext, app: App) -> None:
    await state.clear()
    await _show(callback, *await _mods_view(app))
    await callback.answer()


@router.callback_query(F.data == "set:mods:add", IsOwner())
async def mods_add(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(SettingsFlow.moderator)
    await callback.answer()
    await callback.message.answer(texts.MODERATOR_PROMPT)


@router.message(SettingsFlow.moderator, IsOwner(), IsInput())
async def mods_save(message: Message, state: FSMContext, app: App) -> None:
    username = (message.text or "").strip()
    result = await app.roles.add_by_username(username, message.from_user.id)
    if result == AddResult.INVALID:
        await message.answer(texts.MODERATOR_INVALID)
        return
    await state.clear()
    match result:
        case AddResult.ADDED:
            name = texts.esc("@" + username.lstrip("@"))
            await message.answer(texts.MODERATOR_ADDED.format(name=name))
        case AddResult.ALREADY:
            await message.answer(texts.MODERATOR_ALREADY)
        case AddResult.IS_OWNER:
            await message.answer(texts.MODERATOR_IS_OWNER)
    text, markup = await _mods_view(app)
    await message.answer(text, reply_markup=markup)


@router.callback_query(F.data.startswith("set:mods:rm:"), IsOwner())
async def mods_remove(callback: CallbackQuery, state: FSMContext, app: App) -> None:
    removed, user_id = await app.roles.remove(int(callback.data.rsplit(":", 1)[1]))
    if removed and user_id:
        # End anything they had open and take the commands out of their menu.
        key = StorageKey(bot_id=callback.bot.id, chat_id=user_id, user_id=user_id)
        await state.storage.set_state(key, None)
        await state.storage.set_data(key, {})
        await clear_menu(app, user_id)
    await callback.answer(texts.MODERATOR_REMOVED)
    await _show(callback, *await _mods_view(app))
