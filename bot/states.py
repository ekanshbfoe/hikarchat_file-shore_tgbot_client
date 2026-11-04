"""Conversation steps."""

from aiogram.fsm.state import State, StatesGroup


class Collect(StatesGroup):
    messages = State()


class Batch(StatesGroup):
    first = State()
    last = State()


class Special(StatesGroup):
    name = State()


class ShortenerFlow(StatesGroup):
    url = State()


class BroadcastFlow(StatesGroup):
    message = State()


class SettingsFlow(StatesGroup):
    caption = State()
    button = State()
    shortener_site = State()
    shortener_key = State()
    update_channel = State()
    moderator = State()


class ForceSubFlow(StatesGroup):
    pick_chat = State()
    link = State()
    name = State()
    rename = State()
