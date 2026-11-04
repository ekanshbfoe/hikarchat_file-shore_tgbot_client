# File Store Bot

A Telegram file store bot for one client. Files live in a private Telegram channel and are
delivered through shareable links. Before getting files, users can be required to join any number
of Telegram channels and groups, and to subscribe to any number of YouTube and TikTok channels.

The client's own guide, with no technical language, is in [docs/CLIENT_GUIDE.md](docs/CLIENT_GUIDE.md).

## Rules for working on this project

- **No technical messages to users or the client.** Every word the bot says lives in
  `bot/texts.py`, and `tests/test_texts.py` rejects error codes and technical words. Details go to
  the logs and the optional `DEV_CHAT_ID` chat, never to the client.
- **Atomic commits.** One logical change per commit, with tests passing.

## How it works

| Area | Where | Notes |
|---|---|---|
| Files | Backup channel | Copied inside Telegram, so large files work. The database stores pointers only. |
| Real data | Cloud Postgres | Users, roles, links, settings, force-sub channels, jobs, conversations. |
| Local cache | SQLite | Read first, then Postgres. Render wipes the disk, so it is only ever a cache. |
| Long jobs | `jobs` table | `/broadcast` and `/batch` save progress and resume after a restart. |
| Screenshots | `bot/services/verification.py` | Tesseract, forgiving by design, 8 second limit. |

**Force subscribe versions.** Each channel has a version, and a verification counts only while its
version matches. Replacing a channel or using "Ask everyone again" affects that channel alone.
Removing and re-adding the same channel keeps earlier verifications.

**Screenshot rules.** A screenshot fails only if it clearly shows a not-subscribed button, or if
nothing relevant can be read. If the check breaks or times out, the person passes. After
`SCREENSHOT_MAX_ATTEMPTS` failures (default 3) the person passes anyway so nobody is ever stuck,
which also means random images can get through. Set it to `0` to keep asking.

## Deploying to Render

1. Create a free Postgres database on Neon or Supabase.
2. Create a private Telegram channel and add the bot as an admin who can post.
3. On Render, create a Blueprint from this repo. It reads `render.yaml`.
4. Fill in the settings below. Migrations and the webhook are handled at startup.
5. Point UptimeRobot at `https://<service>.onrender.com/health` every 5 minutes.

| Setting | Required | Meaning |
|---|---|---|
| `BOT_TOKEN` | Yes | From @BotFather |
| `OWNER_ID` | Yes | The client's numeric Telegram ID |
| `BACKUP_CHANNEL_ID` | Yes | The private channel, starting with `-100` |
| `DATABASE_URL` | Yes | Any `postgres://` style URL |
| `DATABASE_DIRECT_URL` | No | Non-pooled URL, used only for migrations |
| `MODERATOR_USERNAMES` | No | Comma separated. Applied once each, so removed moderators stay removed |
| `DEV_CHAT_ID` | No | Where failure details go. Never give this chat to the client |
| `SCREENSHOT_MAX_ATTEMPTS` | No | See above |

Keep only one always-awake free service in the Render workspace: one uses about 744 of the 750 free
hours a month. Render can still restart free services at any time, which the bot is built to handle.

**Changing the bot's username breaks older links**, because each link includes it.

## Development

```bash
uv venv --python 3.13 .venv
uv pip install --python .venv/bin/python -e '.[dev]'
sudo apt-get install tesseract-ocr tesseract-ocr-hin
docker run -d --name fsb-pg -e POSTGRES_PASSWORD=test -e POSTGRES_DB=fsb_test \
  -p 55432:5432 postgres:16-alpine

.venv/bin/python -m pytest
.venv/bin/ruff check .
```

Tests use a real Postgres, the real Tesseract and the real aiogram dispatcher. Only Telegram's
network calls are faked, in `tests/fake_telegram.py`. Set `TEST_DATABASE_URL` to use another database.

To try the bot on a machine with no public address, set `RUN_MODE=polling` and use a test bot.
